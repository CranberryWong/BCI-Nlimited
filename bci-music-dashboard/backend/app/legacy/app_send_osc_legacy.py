import os
import time
import threading
import queue
from pathlib import Path
from typing import Optional, Tuple, List

from flask import Flask, jsonify, render_template
from pythonosc import udp_client  # 新增：导入OSC客户端

import pyxdf
import numpy as np
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import joblib

# =========================
# 全局配置：Flask + OSC
# =========================

app = Flask(__name__)

# 前端轮询的共享状态：实时 valence / arousal
latest_values = {
    "valence": 5,   # 默认值（1~9 中点）
    "arousal": 5,
    "finished": False,
    "started": False,
    "prob0": None,
    "prob1": None,
}

# 新增：OSC 客户端配置（修改为你的目标服务器信息）
OSC_TARGET_IP = "127.0.0.1"  # 目标服务器IP（如远程服务器需改为实际公网/内网IP）
OSC_TARGET_PORT = 57120       # 目标服务器OSC监听端口（可自定义，需与服务器保持一致）
OSC_MESSAGE_ADDRESS = "/eeg/valence_arousal"  # OSC消息地址（用于服务器区分不同数据）

# 全局OSC客户端实例
osc_client = None

last_update_time = None
has_received_data = False
NO_DATA_TIMEOUT = 3.0

# 推理窗口相关参数（1s=300 点，约 6 个文件）
WINDOW_SIZE = 300
MAX_PACKETS_PER_WINDOW = 6
EXPECTED_CHANNELS = 19
eeg_buffer: list[np.ndarray] = []
MIN_PRED_INTERVAL = 1.0  # 最小预测间隔（秒），确保每秒发送一次数据
last_pred_time = -1e9    # 控制输出频率（秒，初始很早以前）

_latest_lock = threading.Lock()

# =========================
# 新增：OSC 消息发送辅助函数
# =========================
def init_osc_client():
    """初始化OSC客户端，全局唯一实例"""
    global osc_client
    try:
        osc_client = udp_client.SimpleUDPClient(OSC_TARGET_IP, OSC_TARGET_PORT)
        print(f"[OSC] 客户端初始化成功，目标：{OSC_TARGET_IP}:{OSC_TARGET_PORT}")
    except Exception as e:
        print(f"[ERROR] OSC客户端初始化失败：{str(e)}")
        osc_client = None

def send_osc_data(valence: int, arousal: int, prob0: Optional[float] = None, prob1: Optional[float] = None):
    """
    向目标OSC服务器发送valence、arousal及置信度数据
    :param valence: 效价（1~9 整数）
    :param arousal: 唤醒度（1~9 整数）
    :param prob0: 类别0置信度（可选）
    :param prob1: 类别1置信度（可选）
    """
    if osc_client is None:
        print("[WARN] OSC客户端未初始化，跳过数据发送")
        return

    try:
        # 构造OSC消息数据（格式可根据服务器需求调整，支持int/float/bool等基本类型）
        osc_payload = [
            int(valence),
            int(arousal),
            float(prob0) if prob0 is not None else 0.0,
            float(prob1) if prob1 is not None else 0.0
        ]
        
        # 发送OSC消息（地址 + 数据载荷）
        osc_client.send_message(OSC_MESSAGE_ADDRESS, osc_payload)
        
        # 打印发送日志（可选，用于调试）
        print(f"[OSC] 已发送数据 -> 地址：{OSC_MESSAGE_ADDRESS}，内容：{osc_payload}")
    except Exception as e:
        print(f"[ERROR] OSC数据发送失败：{str(e)}")

# =========================
# 原有函数：更新前端数据 + 新增OSC发送调用
# =========================
def update_latest(valence: int, arousal: int, prob0: Optional[float] = None, prob1: Optional[float] = None):
    """更新给前端的最新情绪数值（1~9 整数），可附带置信度，并发送至OSC服务器"""
    global last_update_time, has_received_data
    with _latest_lock:
        latest_values["valence"] = int(valence)
        latest_values["arousal"] = int(arousal)
        latest_values["started"] = True
        latest_values["prob0"] = float(prob0) if prob0 is not None else None
        latest_values["prob1"] = float(prob1) if prob1 is not None else None
    last_update_time = time.time()
    has_received_data = True

    # 核心修改：更新数据后，立即发送至OSC目标服务器（确保每秒一次）
    send_osc_data(valence, arousal, prob0, prob1)

def mark_started():
    """确保前端看到已经开始采集，即使还没产生预测结果"""
    global last_update_time, has_received_data
    with _latest_lock:
        latest_values["started"] = True
    # 不更新 valence/arousal，只标记状态

def mark_finished():
    """实验结束时调用（前端会停止轮询）"""
    with _latest_lock:
        latest_values["finished"] = True

# =========================
# Flask 路由（无修改）
# =========================
@app.route("/")
def index():
    """返回前端页面，假设 templates/index.html 已经按之前版本准备好"""
    return render_template("index.html")

@app.route("/latest")
def latest():
    """给前端的 JSON 接口：返回最新 valence / arousal / finished"""
    with _latest_lock:
        return jsonify(latest_values)

# =========================
# 模型与数据相关部分（无核心修改）
# =========================
# 载入离线训练好的 valence 二分类模型（含 StandardScaler + MLP）
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "train/mlp_valence_model.pkl"
MODEL_PATH = Path(os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH))
model_valence = None  # 稍后加载

class XdfDataHandler:
    """XDF 数据处理器（解析和处理脑电/眼动数据）"""
    @staticmethod
    def parse_xdf(file_path: str) -> Optional[Tuple[dict, list]]:
        """解析 XDF 文件，返回 (header, streams) 或 None"""
        try:
            if not os.path.exists(file_path):
                print(f"[ERROR] 文件不存在：{file_path}")
                return None

            data, header = pyxdf.load_xdf(file_path, verbose=False)
            return header, data

        except Exception as e:
            print(f"[ERROR] 解析 XDF 文件失败 {file_path}：{str(e)}")
            return None

def read_eeg_packet(file_path: Path):
    """
    读取单个 EEG 数据包，累积 6 个文件（约 1s）后送入模型预测。
    模型输出 0/1 -> (valence, arousal) 映射为 (9,9)/(1,9)。
    """
    global last_pred_time
    if model_valence is None:
        print("[WARN] 模型尚未加载，忽略该包")
        return
    print(f"[EEG] New packet: {file_path}")
    mark_started()  # 一旦收到包就标记已开始
    xdf_result = XdfDataHandler.parse_xdf(str(file_path))
    if not xdf_result:
        return

    header, data = xdf_result
    eeg_segment = np.asarray(data[0]["time_series"])  # shape: [T, channels]

    # 过滤通道，保持与离线训练一致（去掉 A1/A2/X1/X2/X3/TRG）
    exclude_labels = {"A1", "A2", "X3", "X2", "X1", "TRG"}
    try:
        channels = data[0]["info"]["desc"][0]["channels"][0]["channel"]
        labels = [ch["label"][0] for ch in channels]
        keep_mask = np.array([lbl not in exclude_labels for lbl in labels], dtype=bool)
        eeg_segment = eeg_segment[:, keep_mask]
    except Exception:
        pass

    # 确保通道数与训练一致
    if eeg_segment.shape[1] > EXPECTED_CHANNELS:
        eeg_segment = eeg_segment[:, :EXPECTED_CHANNELS]
    elif eeg_segment.shape[1] < EXPECTED_CHANNELS:
        print(f"[WARN] 通道数不足 {EXPECTED_CHANNELS}, 当前 {eeg_segment.shape[1]}，跳过该包")
        return

    # 累积 6 个文件（约 1s）后再预测
    eeg_buffer.append(eeg_segment)
    # 只保留最近的若干个包
    max_packets = MAX_PACKETS_PER_WINDOW * 2
    if len(eeg_buffer) > max_packets:
        eeg_buffer.pop(0)

    # 计算当前累计样本数
    total_len = sum(seg.shape[0] for seg in eeg_buffer[-MAX_PACKETS_PER_WINDOW:])
    if total_len < WINDOW_SIZE:
        return  # 未满 1s，继续等待

    # 控制输出频率：至少间隔 1s（确保每秒发送一次OSC数据）
    now = time.monotonic()
    if now - last_pred_time < MIN_PRED_INTERVAL:
        return

    # 拼接最近的窗口，截取最后 WINDOW_SIZE 个采样点
    concat = np.concatenate(eeg_buffer[-MAX_PACKETS_PER_WINDOW:], axis=0)
    if concat.shape[0] > WINDOW_SIZE:
        concat = concat[-WINDOW_SIZE:, :]

    # 窗口级 z-score（按通道），与训练保持一致
    mean = concat.mean(axis=0, keepdims=True)
    std = concat.std(axis=0, keepdims=True) + 1e-6
    window_norm = (concat - mean) / std

    X_flattened = window_norm.reshape(1, -1)

    # 模型预测概率
    probs = model_valence.predict_proba(X_flattened)  # shape [1, 2]
    prob0, prob1 = float(probs[0, 0]), float(probs[0, 1])
    pred = 0 if prob0 >= prob1 else 1

    # 置信度映射：低置信度保持中性，高置信度靠两端（valence <=3 / >=7）且 arousal 偏高
    conf = max(prob0, prob1)  # 0.5 ~ 1
    if conf < 0.6:
        # 低置信度：在 4~6 间浮动，方向由 prob0-prob1 决定；arousal 在 1~4
        delta = (prob0 - prob1) * 2.0  # -1 ~ 1
        valence = 5.0 + delta          # 约 4~6
        arousal = 1.0 + (conf - 0.5) / 0.1 * 3.0  # 0.5->1, 0.6->4
        valence = float(np.clip(valence, 4, 6))
        arousal = float(np.clip(arousal, 1, 4))
    else:
        # conf 从 0.6 -> 1 映射到 arousal 6 -> 9
        base = (conf-0.6)/0.4
        curve = np.log1p(base*4)/np.log1p(4)
        scale = (conf - 0.6) / 0.4  # 0 ~ 1
        if pred == 0:
            # 0.6 -> 7, 1.0 -> 9
            valence = 7 + curve * 1.8
            arousal = 6 + scale * 2.5
        else:
            # 0.6 -> 3, 1.0 -> 1
            valence = 3 - curve * 1.8
            arousal = 5 + scale * 2.5

        valence = float(np.clip(valence, 1, 9))
        arousal = float(np.clip(arousal, 1, 9))

    # 取整给前端（同时用于OSC发送）
    valence = int(round(valence))
    arousal = int(round(arousal))

    print(f"Pred={pred} (p0={prob0:.3f}, p1={prob1:.3f}) -> Valence={valence}, Arousal={arousal}")

    # 更新给前端 + 自动发送OSC（update_latest内部已集成OSC发送）
    update_latest(valence, arousal, prob0=prob0, prob1=prob1)
    last_pred_time = now

    # 生成一次预测后清空/重置缓冲，确保 1s 出 1 个新预测（保证OSC发送频率为每秒一次）
    eeg_buffer.clear()

def read_eye_packet(file_path: Path):
    """读取单个眼动数据包（目前只打印信息，占位）"""
    print(f"[EYE] New packet: {file_path}")
    xdf_result = XdfDataHandler.parse_xdf(str(file_path))
    if not xdf_result:
        return
    header, data = xdf_result
    eye_segment = data[0]["time_series"]
    print(f"[EYE] Segment shape: {np.asarray(eye_segment).shape}")

def run_inference_step():
    """
    如果需要在固定窗口上做额外推理，可以在这里补充逻辑。
    当前版本不做额外处理，只是留接口。
    """
    pass

# =========================
# 会话内的 XDF 监听（无修改）
# =========================
REFRESH_INTERVAL = 0.5  # 推理刷新间隔（秒）

class XdfHandler(FileSystemEventHandler):
    """
    统一监听会话下的 xdf 目录：
    - 根据路径判断是 amplifier(eeg) 还是 eye_tracker(eye)
    - 只关心新建文件
    """
    def __init__(self, packet_queue: "queue.Queue[tuple[str, Path]]"):
        super().__init__()
        self.packet_queue = packet_queue

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        parts = file_path.parts

        if "amplifier" in parts:
            stream_name = "eeg"
        elif "eye_tracker" in parts:
            stream_name = "eye"
        else:
            return

        self.packet_queue.put((stream_name, file_path))

def wait_for_xdf_dir(session_dir: Path,
                     timeout: float = 10.0,
                     check_interval: float = 0.5) -> Optional[Path]:
    """等待 session_dir 下的 xdf 目录出现"""
    xdf_dir = session_dir / "xdf"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if xdf_dir.exists():
            return xdf_dir
        time.sleep(check_interval)

    print(f"[SESSION] xdf directory not found in {session_dir} within {timeout} s.")
    return None

def session_worker(session_dir: Path):
    """
    每个实验会话一个线程：
    - 等待 xdf 目录
    - 递归监听其中所有新建文件
    - 定期取出队列中的包并调用 read_eeg_packet / read_eye_packet
    """
    print(f"[SESSION] Start session worker for: {session_dir}")

    xdf_dir = wait_for_xdf_dir(session_dir)
    if xdf_dir is None:
        return

    print(f"[SESSION]   XDF dir: {xdf_dir}")

    packet_queue: "queue.Queue[tuple[str, Path]]" = queue.Queue()

    handler = XdfHandler(packet_queue)
    observer = Observer()
    observer.schedule(handler, str(xdf_dir), recursive=True)
    observer.start()

    try:
        while True:
            start_t = time.time()

            # 处理本周期内所有新包
            while True:
                try:
                    stream_name, file_path = packet_queue.get_nowait()
                except queue.Empty:
                    break

                if stream_name == "eeg":
                    read_eeg_packet(file_path)
                elif stream_name == "eye":
                    read_eye_packet(file_path)

            run_inference_step()

            if last_update_time is not None and time.time() - last_update_time > NO_DATA_TIMEOUT:
                mark_finished()
                print("FINISHED")
                break

            spent = time.time() - start_t
            sleep_time = REFRESH_INTERVAL - spent
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print(f"[SESSION] Stop session worker for: {session_dir}")
    finally:
        observer.stop()
        observer.join()

# =========================
# 根目录监听：发现新会话（修复路径 + 自动创建目录）
# =========================
# 根目录（可用环境变量 XDF_ROOT_DIR 覆盖）
# 关键修改1：修正默认路径的用户名（ddd → SJTU）
DEFAULT_ROOT = Path(r"C:\Users\SJTU\.leaf\record")
ROOT_DIR = Path(os.getenv("XDF_ROOT_DIR", DEFAULT_ROOT))
SESSION_KEYWORD = "BCI"  # 只对包含该关键字的会话目录启动监听

# 关键修改2：新增目录检查与创建函数
def ensure_directory_exists(dir_path: Path):
    """确保指定目录存在，不存在则自动创建"""
    if not dir_path.exists():
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"[DIR] 目录不存在，已自动创建：{dir_path}")
        except Exception as e:
            print(f"[ERROR] 创建目录失败 {dir_path}：{str(e)}")
            raise
    else:
        print(f"[DIR] 监控目录已存在：{dir_path}")

class RootHandler(FileSystemEventHandler):
    """监听根目录 ROOT_DIR，有新建会话目录时启动 session_worker"""
    def on_created(self, event):
        if not event.is_directory:
            return

        session_path = Path(event.src_path)
        name = session_path.name

        if SESSION_KEYWORD and SESSION_KEYWORD not in name:
            return

        print(f"[ROOT] New session directory detected: {session_path}")

        t = threading.Thread(
            target=session_worker,
            args=(session_path,),
            daemon=True,
        )
        t.start()

def watch_root(root_dir: Path):
    """在单独线程中运行：持续监听根目录"""
    # 关键修改3：监听前先确保目录存在
    ensure_directory_exists(root_dir)
    
    print(f"[ROOT] Watching root directory: {root_dir}")
    observer = Observer()
    handler = RootHandler()
    observer.schedule(handler, str(root_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[ROOT] Stopping root watcher...")
    finally:
        observer.stop()
        observer.join()

def start_root_watcher():
    """供线程调用的包装函数"""
    watch_root(ROOT_DIR)

# =========================
# 主入口：新增OSC客户端初始化
# =========================
if __name__ == "__main__":
    # 1. 初始化OSC客户端（优先于模型加载，确保发送功能就绪）
    init_osc_client()

    # 2. 加载离线训练的模型
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"找不到模型文件: {MODEL_PATH}")
    model_valence = joblib.load(MODEL_PATH)
    print(f"已加载模型: {MODEL_PATH}")

    # 3. 启动根目录监听线程（后台）
    t_root = threading.Thread(target=start_root_watcher, daemon=True)
    t_root.start()

    # 4. 启动 Flask Web 服务
    #    host="0.0.0.0" 方便局域网其它设备访问；开发阶段可用默认 127.0.0.1
    app.run(host="0.0.0.0", port=5000, debug=False)  # 注意：生产环境关闭debug，避免多线程冲突