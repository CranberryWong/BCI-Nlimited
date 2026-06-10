# 和鸣-BCI Dashboard

和鸣-BCI Dashboard 是一个用于脑机接口情绪驱动音乐生成的 Web Dashboard。系统接收实时
`[valence, arousal, prob0, prob1]` 四元组，映射为情绪状态，并进一步生成旋律、和声、
低音、鼓点、镲片、Pad 与控制事件，输出到 OSC 或 MIDI，同时保存可复现实验记录。

## 项目结构

- `backend/app/bci`：OSC 输入、模拟器、XDF 监听、模型推理与情绪映射。
- `backend/app/music`：YAML 音乐配置、多音轨生成引擎、MIDI/OSC 输出与录制。
- `frontend/src/views/Dashboard`：情绪监测、音轨编辑、输出测试、录制和配置界面。
- `models`：模型文件放置目录；目录可提交，`.pkl` 模型文件默认忽略。
- `backend/app/legacy`：保留的旧 Flask OSC 程序和旧测试发送器副本。

## 模型文件

请将情绪模型文件放到：

```text
models/mlp_valence_model.pkl
```

默认 `MODEL_PATH` 为 `models/mlp_valence_model.pkl`。也可以在 `.env` 中改为绝对路径。
如果模型缺失，后端仍可启动，Dashboard 会显示 `model_missing`，模拟器仍可使用；
点击 `Start Model` 时会返回明确错误。

## 本地启动

1. 创建环境变量文件：

   ```bash
   cd bci-music-dashboard
   cp .env.example .env
   ```

2. 启动后端：

   ```bash
   cd backend
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
   ```

   FastAPI 文档地址为 `http://127.0.0.1:8001/docs`。

3. 启动前端：

   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

   打开 `http://127.0.0.1:5173`。

4. 仅做演示时点击 `Start Simulator`，情绪曲线和 Music Events 会通过
   `/ws/realtime` 实时更新。

## Windows 启动

在 PowerShell 中执行：

```powershell
Copy-Item .env.example .env
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

另开一个 PowerShell 进入 `frontend`，执行 `npm install` 和 `npm run dev`。
真实 EEG 使用前，请把 `.env` 中的 `XDF_ROOT_DIR` 设置为 Leaf 或采集程序实际写入
XDF 文件的目录。

## macOS 启动

本地开发命令与上文一致。若需要虚拟 MIDI 输出，可在“音频 MIDI 设置”中创建 IAC Bus，
然后刷新 `GET /api/outputs/midi-ports`，把目标音轨设置为 MIDI 输出，并把输出模式设为
包含 MIDI 的模式。没有 MIDI 设备时，系统会进入 mock mode，不会崩溃。

## Docker Compose

推荐在目标台式机部署时使用 Docker。容器结构为：

- `frontend`：Vue 生产构建，由 Nginx 提供页面，并代理 `/api` 与 `/ws`。
- `backend`：FastAPI、OSC 输入、模型推理与音乐引擎。
- `models`：宿主机只读挂载，镜像重建不会丢失模型。
- `backend/data`：宿主机持久化挂载，保存 Preset 和 Session。
- `xdf-records`：宿主机采集目录挂载到容器内 `/xdf-records`。

### 有网络的目标电脑

安装 Docker Desktop 后，把项目源码复制或从 Gitee 克隆到目标电脑，然后：

```bash
cd bci-music-dashboard
cp .env.example .env
docker compose up --build
```

Windows PowerShell 可直接运行：

```powershell
cd bci-music-dashboard
.\scripts\start-docker.ps1
```

如果真实 XDF 位于 Windows 的 Leaf 目录，在 `.env` 中设置：

```env
HOST_XDF_ROOT_DIR=C:/Users/SJTU/.leaf/record
```

Compose 会暴露前端 `5173`、后端 `8001` 和 UDP 输入 OSC 端口 `8000`。访问：

```text
Dashboard: http://127.0.0.1:5173
API Docs: http://127.0.0.1:8001/docs
```

### 离线或网络不稳定的目标电脑

在开发机项目目录执行：

```bash
./scripts/export-docker-bundle.sh linux/amd64
```

脚本会生成 `docker-bundle/`，其中包括：

- Linux/AMD64 后端和前端镜像压缩包；
- `docker-compose.yml` 与 `.env.example`；
- Windows 启动脚本 `start-windows.ps1`；
- 模型文件（如果存在）；
- 当前 Preset 和 Session 数据目录。

将整个 `docker-bundle` 文件夹通过移动硬盘、局域网或网盘传到 Windows 目标电脑。
安装并启动 Docker Desktop，切换到 Linux containers，然后在 PowerShell 执行：

```powershell
cd D:\path\to\docker-bundle
Set-ExecutionPolicy -Scope Process Bypass
.\start-windows.ps1
```

脚本会执行 `docker load` 和 `docker compose up -d --no-build`，目标电脑不需要访问
Python、npm 或镜像仓库。

停止和更新：

```powershell
docker compose down
docker compose ps
docker compose logs -f
```

Docker Desktop 中直接访问 loopMIDI 等宿主机 MIDI 设备不稳定。容器部署推荐输出 OSC
到宿主机，再由 Max/MSP 或本地 MIDI Bridge 转换为 MIDI。Compose 已将默认 localhost
OSC 输出转换为 `host.docker.internal`。

## 输入模式

- 真实模型：配置 `XDF_ROOT_DIR`，放置模型文件，点击 `Start Model`。
- 模拟器：点击 `Start Simulator`，使用本地模拟情绪流。
- OSC 输入：向 `BCI_INPUT_OSC_IP:BCI_INPUT_OSC_PORT` 发送
  `/eeg/valence_arousal` 四个参数，默认输入端口为 `8000`。

输入 OSC 端口和输出 OSC 端口是两件事。默认输入端口为 `8000`；默认输出目标常用于
Max/MSP，为 `127.0.0.1:57120`，并且每条音轨都可以覆盖自己的输出 IP 与端口。

## 音乐配置

默认音乐参数集中在：

```text
backend/app/config/music_defaults.yaml
```

这份 YAML 保存全局参数、情绪配置、默认音轨、可编辑参数范围、音阶和输出规则。
运行时优先级为：

1. Dashboard 中刚刚应用的实时修改。
2. 当前加载的 preset。
3. `music_defaults.yaml`。
4. Python 代码中的安全 fallback。

在 Dashboard 的 `Music Config` 中可以实时修改 BPM、Root Note、Scale、Quantization、
情绪参数、音轨参数和映射权重。点击 `Apply` 后无需重启后端；点击 `Save Preset` 会把
当前配置快照保存到 `backend/data/presets`。配置也可以导出为 YAML，或从 YAML/JSON 导入。

每条非打击乐音轨有两个相互独立的密度参数：

- `Onset Density`：时间事件密度，控制一段时间内触发音符事件的频繁程度。
- `Polyphony`：纵向复音数，控制每次触发同时发出多少个音；旋律按音阶叠加声部，
  Chord/Pad 扩展和弦声部，Bass 优先叠加五度与八度。

两项设置都会随 `Save Preset` 保存。

## 输出与测试

OSC 输出地址包括：

```text
/music/track/{track_id}/note
/music/track/{track_id}/control
/music/emotion
/music/global
```

连接 Max/MSP 时，可监听音轨目标端口，例如 `57120`，并解析 note payload：

```text
[event_type, pitch, velocity, duration_ms, midi_channel]
```

Dashboard 的 `Test Output` 按钮会向所选音轨发送测试音符。MIDI 输出使用 `mido` 和
`python-rtmidi`；设备不可用时，接口会报告 mock mode。

## 录制与复现

Session API：

- `POST /api/sessions/start`
- `POST /api/sessions/stop`
- `GET /api/sessions`
- `GET /api/sessions/{id}/download?format=mid|csv|emotion-jsonl|music-jsonl|config`

每次停止录制后，会保存：

- 情绪时间序列 CSV；
- 情绪时间线 JSONL；
- Music Events 事件日志 JSONL；
- 标准 MIDI 文件；
- 当次使用的 `music_config_snapshot.yaml`。

这些文件能够还原实验输入、生成决策、MIDI 输出和当次音乐配置。

## Preset 与配置 API

内置 preset 包括 Ambient Neurofeedback、Piano Emotion Melody、Percussive Arousal
和 Max/MSP OSC Bridge。Preset 本质上是当前 YAML 音乐配置的一份快照。

主要配置 API：

- `GET /api/music/config`
- `PUT /api/music/config`
- `POST /api/music/config/reset`
- `GET /api/music/config/export`
- `POST /api/music/config/import`
- `PATCH /api/tracks/{track_id}`
- `POST /api/tracks/{track_id}/reset`

## 旧代码兼容

旧 `app_send_osc.py` 与 `send_osc_fortest.py` 已复制到 `backend/app/legacy`。主程序不会
导入它们，但旧代码中的 XDF 解析、模型窗口推理、四元组 payload 和模拟器 payload 逻辑
已经迁移进模块化后端。
