# RDK550P-MOSS

基于 [D-Robotics RDK X5](https://developer.d-robotics.cc/rdk_doc/Quick_start/hardware_introduction/rdk_x5) 的桌面 AI 机器人伴侣。致敬《流浪地球》中的 MOSS。

它有眼睛（MIPI 摄像头）、能转头（双轴舵机云台）、能听你说话（语音唤醒 + ASR）、能跟你聊天（LLM 对话）、还会跳舞。

> **Agent 部署提示：** 如果你是 AI Agent 且需要在 RDK X5 上自动部署此项目，直接阅读 [`DEPLOY.md`](DEPLOY.md)，按步骤执行即可。

## 功能

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
| 摄像头 | IMX477 MIPI 模组 | [购买](https://detail.tmall.com/item.htm?id=636204625264) | MIPI CSI 排线连接 |
| 舵机 x2 | PTK7465 数字舵机 | — | Yaw（左右）+ Pitch（上下） |
| USB 音频模块 | USB 麦克风+扬声器一体模块 | [购买](https://item.taobao.com/item.htm?id=909788853795) | 免驱，含麦克风和扬声器 |
| 云台支架 + 外壳 | SolidWorks 2024 3D 模型 | [`hardware/3d-model/`](hardware/3d-model/) | 含装配体 + 全部零件，3D 打印 |
| 供电 | 5V/3A USB-C | — | RDK X5 标准供电 |

详细物料清单和接线说明见 [`hardware/BOM.md`](hardware/BOM.md)

## 快速开始

### 前提

- RDK X5 已刷好官方系统（Ubuntu 22.04）
- 硬件已接线完成
- 有网络连接

### 部署

```bash
git clone https://github.com/RDK550W/RDK550P-MOSS.git
cd RDK550P-MOSS
sudo bash setup/install.sh
```

一键安装脚本会自动完成所有配置。详细分步说明见 [`DEPLOY.md`](DEPLOY.md)。

## 项目结构

```
RDK550P-MOSS/
├── DEPLOY.md                # Agent/人类 分步部署指南
├── README.md                # 项目介绍
├── LICENSE                  # MIT
├── hardware/
│   ├── BOM.md               # 物料清单 + 接线说明
│   └── 3d-model/            # SolidWorks 2024 外壳+云台模型
│       ├── RDK550W装配体.SLDASM
│       ├── 标准件/           # 舵机、舵盘参考模型
│       └── 零件库/           # 3D 打印零件 (P00~P12 + 支座)
├── voice-assistant/         # 语音助手（核心）
│   ├── voice_assistant.py   # 主程序
│   ├── speaker_id.py        # 声纹识别
│   ├── speaker_diarization.py  # 说话人分离
│   ├── enroll_speaker.py    # 声纹注册
│   ├── start.sh             # 启动脚本
│   ├── sounds/              # 音效
│   └── models/              # AI 模型 (gitignored, 由脚本下载)
├── scripts/                 # 工具脚本
│   ├── dance.py             # 舵机舞蹈（含 move_eased 标准实现）
│   ├── dance_jntm.py        # 音乐同步跳舞示例
│   ├── idle_motion.py       # 闲时随机动作
│   ├── snap.py              # MIPI 摄像头拍照
│   └── camera_test.py       # 摄像头测试
├── setup/                   # 安装脚本
│   ├── install.sh           # 一键安装
│   ├── download_models.sh   # 模型下载
│   ├── setup_alsa.sh        # ALSA 音频配置
│   ├── setup_pwm.sh         # PWM 舵机初始化
│   └── requirements.txt     # Python 依赖
├── openclaw-templates/      # OpenClaw 配置模板
│   ├── SOUL.md.template     # 机器人性格
│   ├── USER.md.template     # 主人信息
│   ├── IDENTITY.md.template # 机器人身份
│   ├── TOOLS.md.template    # 硬件备忘
│   ├── HEARTBEAT.md.template # 心跳任务
│   └── AGENTS.md.template   # 工作空间规则
├── systemd/                 # 系统服务
│   └── voice-assistant.service
├── tutorials/               # 详细教程
│   ├── rdk-x5-voice-assistant-tutorial.md
│   ├── rdk-x5-servo-pwm-tutorial.md
│   ├── rdk-x5-mipi-camera-tutorial.md
│   ├── rdk-x5-tts-tutorial.md
│   ├── rdk-x5-bpu-yolov5-tutorial.md
│   └── rdk-x5-gpio-tutorial.md
└── docs/
    ├── architecture.md      # 系统架构
    └── troubleshooting.md   # 踩坑指南
```

## 系统架构

```
┌──────────────────────────────────────────┐
│              OpenClaw (AI 大脑)            │
│  LLM 对话 · 记忆系统 · 定时任务 · 工具调用  │
└──────────────┬───────────────────────────┘
               │ openclaw agent CLI
┌──────────────▼───────────────────────────┐
│          Voice Assistant (守护进程)        │
│  Silero VAD → SenseVoice ASR → 3DSpeaker │
│  → OpenClaw Agent → edge-tts → aplay     │
└──────────────────────────────────────────┘
    │              │              │
┌───▼────┐  ┌─────▼──────┐  ┌───▼──────┐
│USB 音频 │  │ PTK7465 x2 │  │ IMX477   │
│麦克风+  │  │ 舵机云台    │  │ 摄像头    │
│扬声器   │  │ (PWM)      │  │ (MIPI)   │
└────────┘  └────────────┘  └──────────┘
```

详细架构说明见 [`docs/architecture.md`](docs/architecture.md)

## 自定义

- **唤醒词** — 修改 `voice_assistant.py` 中的唤醒词列表
- **TTS 声音** — 修改 edge-tts 的 voice 参数（`edge-tts --list-voices` 查看可用声音）
- **舞蹈动作** — 参考 `scripts/dance.py` 的 `move_eased()` 编写新动作
- **摄像头** — 结合 BPU 模型做目标检测等（参考 tutorials）
- **AI 人格** — 编辑 OpenClaw 的 `SOUL.md`

## 踩坑指南

详见 [`docs/troubleshooting.md`](docs/troubleshooting.md)

## 致谢

- [D-Robotics](https://developer.d-robotics.cc/) — RDK X5 硬件平台
- [OpenClaw](https://github.com/openclaw/openclaw) — AI Agent 运行时
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — 离线语音识别
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — ASR 模型
- [3D-Speaker](https://github.com/alibaba-damo-academy/3D-Speaker) — 声纹识别
- [edge-tts](https://github.com/rany2/edge-tts) — 文本转语音
- [Silero VAD](https://github.com/snakers4/silero-vad) — 语音活动检测

## License

MIT
