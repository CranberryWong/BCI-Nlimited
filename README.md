# 和鸣 BCI 音乐系统

本仓库把脑机接口情绪信号转换为实时音乐和可复现的演出记录。当前主流程是
`adaptive_performance`：Dashboard 接收 BCI 或模拟器数据，编排曲式、动机、和声与配器，
统一输出 MIDI、OSC 和会话记录。Google Magenta RealTime 2（MRT2）可在 Apple Silicon
Mac 上为旋律提供实时生成；模型不可用时，演出会按动机规则续演。

## 目录

- [`bci-music-dashboard/`](bci-music-dashboard/README.zh-CN.md)：FastAPI 后端、Vue 前端、
  配置与运行说明（[English](bci-music-dashboard/README.md)）。
- [`magenta-flow/`](magenta-flow/README.md)：MRT2 本机工作进程及独立实验。

## 快速开始

```bash
cd bci-music-dashboard
cp .env.example .env
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

另开终端：

```bash
cd bci-music-dashboard/frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`，启动 `Start Simulator`，再启动
`Start Performance`。使用真实 EEG 时另需配置 XDF 目录和情绪识别模型，详见
[Dashboard 文档](bci-music-dashboard/README.zh-CN.md)。

## Google 模型怎么用？

这里的 Google 模型是 **Magenta RealTime 2**，不是 Gemini API；它在本机运行，
无需 API key。默认使用 `mrt2_small`。在 Apple Silicon Mac 上安装
`magenta-flow` 的独立 Python 环境，并用官方 `mrt models init` 和
`mrt models download` 下载资源及模型，完整命令见
[MRT2 安装说明](magenta-flow/README.md#1-安装与下载-google-模型)。
模型文件保存在 `~/Documents/Magenta/magenta-rt-v2/`，不提交到 GitHub。
Dashboard 启动演出时会自动启动本机 MRT2 工作进程；Windows 和 Docker 使用规则旋律。

官方资料：[模型与下载](https://github.com/magenta/magenta-realtime/blob/main/docs/models.md)、
[模型许可](https://github.com/magenta/magenta-realtime/blob/main/MODEL.md)。
