# RDK550P-MOSS

**M**y **O**wn **S**mart **S**ystem — 基于 RDK X5 的桌面 AI 机器人伴侣

一个跑在 [D-Robotics RDK X5](https://developer.d-robotics.cc/rdk_doc/Quick_start/hardware_introduction/rdk_x5) 上的开源桌面机器人项目。它有眼睛（MIPI 摄像头）、能转头（双轴舵机云台）、能听你说话（语音唤醒 + ASR）、能跟你聊天（LLM 对话）、还会跳舞。

## 它能做什么

- **语音交互** — 唤醒词激活，离线 VAD + SenseVoice ASR，edge-tts 语音回复
- **声纹识别** — 注册说话人后能识别"谁在说话"
- **说话人分离** — 多人对话场景下区分不同说话人
- **舵机控制** — 余弦缓动平滑运动，支持跳舞、环顾、点头等动作
- **音乐同步跳舞** — 节拍检测 + 编舞，跟着音乐节奏动
- **MIPI 摄像头** — 拍照、环境感知
- **LLM 大脑** — 通过 [OpenClaw](https://github.com/openclaw/openclaw) 接入 Claude/GPT 等模型，具备记忆、工具调用、定时任务等能力
- **守护进程** — systemd 管理，崩溃自动重启，开机自启

## 硬件清单

| 组件 | 型号 | 参考链接 | 备注 |
|------|------|---------|------|
| 运算平台 | D-Robotics RDK X5 | [官方](https://developer.d-robotics.cc/) | 8TOPS BPU，ARM Cortex-A55 |
| 摄像头 | IMX477 MIPI 模组 | [购买链接](https://detail.tmall.com/item.htm?id=636204625264) | 通过 MIPI CSI 接口连接 |
| 舵机 x2 | PTK7465 数字舵机 | — | 一个 yaw（左右），一个 pitch（上下） |
| USB 麦克风 | USB 音频模块 | [购买链接](https://item.taobao.com/item.htm?id=909788853795) | 免驱即插即用 |
| 扬声器 | 任意 3.5mm/USB 音箱 | — | 或复用 USB 音频模块的输出 |
| 云台支架 | 3D 打印 / 舵机支架 | TODO | 固定两个舵机的机械结构 |
| 供电 | 5V/3A USB-C | — | RDK X5 标准供电 |

## 接线

```
RDK X5 40-Pin Header:
  Pin 32 (PWM6) ──→ 舵机1 信号线 (Yaw / 左右)
  Pin 33 (PWM7) ──→ 舵机2 信号线 (Pitch / 上下)
  Pin 2  (5V)   ──→ 舵机供电 VCC (两个舵机并联)
  Pin 6  (GND)  ──→ 舵机供电 GND

USB:
  USB 口 ──→ USB 麦克风/音频模块

MIPI CSI:
  CSI 接口 ──→ IMX477 摄像头排线
```

> 注意：如果两个舵机同时动作电流较大，建议舵机单独供电（5V/2A），共地即可。

## 快速开始

### 前提

- RDK X5 已刷好官方系统（Ubuntu 22.04）
- 硬件已接线完成
- 有网络连接

### 1. 克隆仓库

```bash
git clone https://github.com/RDK550W/RDK550P-MOSS.git
cd RDK550P-MOSS
```

### 2. 一键安装

```bash
sudo bash software/setup/install.sh
```

这会自动：
- 安装系统依赖（alsa-utils, ffmpeg 等）
- 安装 Python 依赖（sherpa-onnx, edge-tts, opencv 等）
- 下载 AI 模型（~2.2GB）
- 配置 ALSA 音频
- 配置 PWM 舵机
- 安装 systemd 服务

### 3. 安装 OpenClaw

```bash
# 安装 OpenClaw（AI 大脑）
curl -fsSL https://get.openclaw.ai | bash

# 首次运行配置
openclaw init
```

参考 [OpenClaw 文档](https://docs.openclaw.ai) 完成 LLM API 配置。

### 4. 配置你的机器人身份

```bash
# 复制模板到 OpenClaw workspace
cp software/openclaw/*.template ~/.openclaw/workspace/
cd ~/.openclaw/workspace
# 把 .template 后缀去掉，填入你自己的信息
for f in *.template; do mv "$f" "${f%.template}"; done
# 编辑 USER.md、SOUL.md、IDENTITY.md 等
```

### 5. 启动

```bash
# 启动语音助手
sudo systemctl start voice-assistant

# 启动 OpenClaw
openclaw gateway start

# 查看状态
sudo systemctl status voice-assistant
openclaw gateway status
```

### 6. 注册你的声纹（可选）

```bash
cd software/voice-assistant
python3 enroll_speaker.py 你的名字
# 按提示说几句话
```

## 项目结构

```
RDK550P-MOSS/
├── README.md                   # 你在看的这个
├── LICENSE
├── hardware/
│   └── BOM.md                  # 详细物料清单
├── software/
│   ├── setup/
│   │   ├── install.sh          # 一键安装脚本
│   │   ├── download_models.sh  # 模型下载
│   │   ├── setup_alsa.sh       # ALSA 音频配置
│   │   ├── setup_pwm.sh        # PWM 舵机初始化
│   │   └── requirements.txt    # Python 依赖
│   ├── voice-assistant/        # 语音助手
│   │   ├── voice_assistant.py  # 主程序
│   │   ├── speaker_id.py       # 声纹识别
│   │   ├── speaker_diarization.py  # 说话人分离
│   │   ├── enroll_speaker.py   # 声纹注册
│   │   ├── start.sh            # 启动脚本（带自动重启）
│   │   └── sounds/             # 音效文件
│   ├── scripts/                # 工具脚本
│   │   ├── dance.py            # 基础舞蹈（含 move_eased 标准实现）
│   │   ├── dance_jntm.py       # 音乐同步跳舞示例
│   │   ├── idle_motion.py      # 闲时随机动作
│   │   ├── snap.py             # MIPI 摄像头拍照
│   │   └── camera_test.py      # 摄像头测试
│   ├── openclaw/               # OpenClaw 配置模板
│   │   ├── AGENTS.md.template
│   │   ├── SOUL.md.template
│   │   ├── USER.md.template
│   │   ├── IDENTITY.md.template
│   │   ├── TOOLS.md.template
│   │   └── HEARTBEAT.md.template
│   └── systemd/                # 系统服务
│       └── voice-assistant.service
├── tutorials/                  # 详细教程
│   ├── rdk-x5-voice-assistant-tutorial.md
│   ├── rdk-x5-servo-pwm-tutorial.md
│   ├── rdk-x5-mipi-camera-tutorial.md
│   ├── rdk-x5-tts-tutorial.md
│   ├── rdk-x5-bpu-yolov5-tutorial.md
│   └── rdk-x5-gpio-tutorial.md
└── docs/
    ├── architecture.md         # 系统架构
    └── troubleshooting.md      # 踩坑指南
```

## 系统架构

```
┌─────────────────────────────────────────────┐
│                 OpenClaw                     │
│         (LLM Gateway + Agent Runtime)       │
│  ┌──────────┐  ┌────────┐  ┌────────────┐  │
│  │ Memory   │  │ Cron   │  │ Tool Skills│  │
│  │ System   │  │ Jobs   │  │ (Feishu,..)│  │
│  └──────────┘  └────────┘  └────────────┘  │
└─────────────────┬───────────────────────────┘
                  │ openclaw agent CLI
┌─────────────────▼───────────────────────────┐
│            Voice Assistant                   │
│  ┌──────┐  ┌──────────┐  ┌──────────────┐  │
│  │ VAD  │→ │ ASR      │→ │ Speaker ID   │  │
│  │Silero│  │SenseVoice│  │ 3DSpeaker    │  │
│  └──────┘  └──────────┘  └──────────────┘  │
│  ┌──────────────────┐  ┌────────────────┐   │
│  │ TTS (edge-tts)   │  │ Wake Word Det  │   │
│  └──────────────────┘  └────────────────┘   │
└─────────────────────────────────────────────┘
       │                          │
  ┌────▼─────┐             ┌─────▼──────┐
  │ USB Mic  │             │ Speaker    │
  │ + ALSA   │             │ (aplay)    │
  └──────────┘             └────────────┘

  ┌──────────┐    ┌─────────────────────┐
  │ IMX477   │    │ PTK7465 Servos x2   │
  │ Camera   │    │ (PWM via sysfs)     │
  │ (MIPI)   │    │ Yaw + Pitch         │
  └──────────┘    └─────────────────────┘
```

## 自定义

- **唤醒词** — 修改 `voice_assistant.py` 中的唤醒词列表
- **TTS 声音** — 修改 edge-tts 的 voice 参数（`edge-tts --list-voices` 查看可用声音）
- **舞蹈动作** — 参考 `dance.py` 的 `move_eased()` 函数编写新动作
- **摄像头用途** — 结合 BPU 模型做目标检测、人脸识别等（参考 tutorials）
- **AI 人格** — 编辑 OpenClaw 的 `SOUL.md`，定义你的机器人性格

## 踩坑指南

详见 [docs/troubleshooting.md](docs/troubleshooting.md)，包含：
- ALSA AGC 必须开启否则 VAD 失效
- USB 声卡不能同时录放
- sherpa_onnx.Alsa 不可靠的替代方案
- PWM 舵机必须用 Python 控制（不能用 shell）
- 模型下载慢的解决办法

## 致谢

- [D-Robotics](https://developer.d-robotics.cc/) — RDK X5 硬件平台
- [OpenClaw](https://github.com/openclaw/openclaw) — AI Agent 运行时
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — 离线语音识别
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — ASR 模型
- [3D-Speaker](https://github.com/alibaba-damo-academy/3D-Speaker) — 声纹识别
- [edge-tts](https://github.com/rany2/edge-tts) — 文本转语音
- [Silero VAD](https://github.com/snakers4/silero-vad) — 语音活动检测

## License

MIT License — 随便用，注明出处就行。
