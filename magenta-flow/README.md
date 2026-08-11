# Magenta Flow

这是一个与主 Dashboard 隔离的 MRT2 实验：代码直接调用 Magenta RealTime 2
模型，逐帧取得音频，用 YIN 检测单旋律，再通过 macOS IAC Bus 把 MIDI 发送到
Logic Pro。它不启动 `MRT2 - Jam.app`，也不从客户端回录音频。

> MRT2 的文字提示不能绝对禁止原始音频出现叠音。本原型保证的是输出 MIDI
> 始终单音：发送新音符前一定先关闭旧音符。

## 1. 安装

需要 Apple Silicon Mac、Python 3.11/3.12，以及已经下载的 MRT2 资源。当前默认目录为：

```text
/Users/chenwang/Documents/Magenta/magenta-rt-v2
```

在终端运行：

```bash
cd /Users/chenwang/Developer/BCI/magenta-flow
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[test]'
```

## 2. 配置 Logic Pro

1. 打开 macOS **音频 MIDI 设置**，选择“窗口 → 显示 MIDI 工作室”。
2. 双击 **IAC 驱动程序**，勾选“设备已在线”，保留或新建一个 Bus。
3. 打开 Logic Pro，新建软件乐器轨并加载马林巴音色。
4. 录音启用该轨；必要时在轨道检查器中限制到 MIDI Channel 1。
5. 先检查脚本能否看到 IAC：

```bash
python run.py --list-midi-ports
python run.py --check
```

如果有多个 IAC Bus，显式指定名称：

```bash
python run.py --check --midi-port 'IAC Driver Bus 1'
```

## 3. 运行

Dashboard 正式运行时会自动管理仅监听 localhost 的工作进程：

```bash
python run_worker.py --host 127.0.0.1 --port 8766 --model mrt2_small
```

它使用 v1 WebSocket 协议接收逐帧 128 音高 pianoroll、编译后的马林巴提示词、
音频增益和可选 Stem；返回单旋律转录事件及帧耗时指标。主 Dashboard 负责最终
音域/调式/强拍/最短音长护栏、规范 MIDI、OSC 分发和故障切换。工作进程退出或
模型不可用时，Transport 不停止，下一乐句从当前动机位置规则续演。

以下命令仍可单独运行原型：

交互输入提示词并运行 30 秒：

```bash
python run.py
```

直接使用简短的快乐马林巴提示词：

```bash
python run.py \
  --prompt 'Joyful fast solo marimba melody, single notes only' \
  --duration 30 \
  --midi-port 'IAC Driver Bus 1'
```

持续运行到按下 `Ctrl+C`：

```bash
python run.py --duration 0
```

只向 Logic 发送 MIDI、不监听 MRT2 原始声音：

```bash
python run.py --no-play-audio
```

脚本退出时会发送 Note Off、CC 123 和 CC 120，避免 Logic 出现卡音。每次运行会在
`outputs/` 保存原始 WAV、实时 MIDI 和带置信度的事件 CSV。保存的 MIDI 使用固定
120 BPM 时间基准来保持真实秒数；现场发送不依赖这个 BPM。

## 4. 参数与性能

- 默认模型为 `mrt2_small`，适合 M1 Pro 实时生成。
- 每个 MRT2 帧为 40ms；YIN 使用约 85ms 的滚动音频窗口。
- 默认预缓冲 5 帧（约 200ms），优先保证音高稳定和连续播放。
- 结束摘要中的模型平均耗时应不高于 40ms；持续高于 40ms 表示本机无法稳定实时。
- 可用 `--temperature`、`--top-k`、`--style-strength` 调整生成，但建议先保留默认值。

## 5. 测试

测试不会启动模型，也不会向真实 MIDI 端口发送消息：

```bash
pytest -q
```
