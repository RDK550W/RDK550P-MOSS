# DEPLOY.md — Agent 自动部署指南

> 本文件是给 AI Agent 读的。如果你是 Agent，按顺序执行以下步骤即可完成部署。
> 目标平台：D-Robotics RDK X5 (aarch64, Ubuntu 22.04)

## 前提条件

- 硬件已接线完成（参考 `hardware/BOM.md` 和 `hardware/wiring.md`）
- RDK X5 已刷好官方 Ubuntu 22.04 系统
- 有网络连接
- 当前用户是 root（或有 sudo 权限）

## Step 1: 安装系统依赖

```bash
apt-get update
apt-get install -y alsa-utils ffmpeg bc python3-pip python3-dev git wget curl
```

## Step 2: 安装 Python 依赖

```bash
pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    sherpa-onnx==1.12.30 \
    edge-tts==7.2.7 \
    numpy==1.26.4 \
    opencv-python==4.11.0.86
```

> 注意：pyaudio 在此平台无法安装（缺少 portaudio19-dev），不需要装。音频采集用 arecord subprocess。

## Step 3: 下载 AI 模型

运行模型下载脚本，模型共约 2.2GB，优先使用 hf-mirror.com 国内镜像：

```bash
bash setup/download_models.sh
```

模型存放于 `voice-assistant/models/`，包含：
- `silero_vad.onnx` — 语音活动检测 (Silero VAD)
- `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/` — ASR (SenseVoice)
- `3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx` — 声纹识别 (3D-Speaker)
- `sherpa-onnx-pyannote-segmentation-3-0/` — 说话人分离 (Pyannote, 可选)

## Step 4: 配置 ALSA 音频

**这一步极其关键，跳过会导致语音助手完全无法工作。**

USB 音频模块（麦克风+扬声器一体）必须开启 AGC，否则采集信号太弱，VAD 无法检测语音：

```bash
# 找到 USB 音频设备的 card 编号（通常是 0）
USB_CARD=$(arecord -l | grep -i "usb\|uac\|jieli" | head -1 | sed 's/card \([0-9]*\):.*/\1/')

# 开启 AGC + 麦克风增益拉满
amixer -c "$USB_CARD" set 'Auto Gain Control' on
amixer -c "$USB_CARD" set 'Mic' 147

# 持久化设置（重启后不丢失）
alsactl store
```

**已知坑：USB 音频模块不支持全双工**（不能同时录音和播放）。voice_assistant.py 已处理此问题——播放 TTS 时暂停录音，播放完再恢复。

## Step 5: 配置 PWM 舵机

```bash
# 导出 PWM 通道并初始化到中心位置 (90°)
PWM_CHIP="/sys/class/pwm/pwmchip0"

for ch in 0 1; do
    echo $ch > "$PWM_CHIP/export" 2>/dev/null || true
    sleep 0.5
    echo 20000000 > "$PWM_CHIP/pwm$ch/period"
    echo 1500000 > "$PWM_CHIP/pwm$ch/duty_cycle"
    echo 1 > "$PWM_CHIP/pwm$ch/enable"
done
```

参数说明：
- Period: 20000000ns (50Hz)
- Duty cycle: 500000ns (0°) ~ 1500000ns (90° 中心) ~ 2500000ns (180°)
- pwm0 = Yaw (左右)，pwm1 = Pitch (上下)
- 安全行程: Yaw ±300000ns, Pitch ±200000ns（相对中心 1500000ns）

**舵机控制铁律：必须用 Python + 余弦缓动，禁止 shell 脚本控制。** Shell 的 fork 开销会导致动作卡顿。参考实现见 `scripts/dance.py` 的 `move_eased()` 函数。

## Step 6: 部署文件到工作目录

```bash
WORK_DIR="/root/.openclaw/workspace"
mkdir -p "$WORK_DIR/voice-assistant/models"
mkdir -p "$WORK_DIR/voice-assistant/sounds"
mkdir -p "$WORK_DIR/scripts"
mkdir -p "$WORK_DIR/media"
mkdir -p "$WORK_DIR/memory"

# 假设本仓库克隆到了 $REPO_DIR
REPO_DIR="$(pwd)"

# 复制语音助手代码
cp "$REPO_DIR/voice-assistant/"*.py "$WORK_DIR/voice-assistant/"
cp "$REPO_DIR/voice-assistant/start.sh" "$WORK_DIR/voice-assistant/"
cp "$REPO_DIR/voice-assistant/sounds/"* "$WORK_DIR/voice-assistant/sounds/"

# 链接模型目录（避免重复占用空间）
ln -sf "$REPO_DIR/voice-assistant/models/"* "$WORK_DIR/voice-assistant/models/"

# 复制工具脚本
cp "$REPO_DIR/scripts/"*.py "$WORK_DIR/scripts/"

# 创建空的声纹数据库
echo '{}' > "$WORK_DIR/voice-assistant/speaker_db.json"
echo '{}' > "$WORK_DIR/voice-assistant/unknown_speakers.json"
```

## Step 7: 安装 OpenClaw

```bash
curl -fsSL https://get.openclaw.ai | bash
openclaw init
```

OpenClaw 是 AI 大脑，提供 LLM 对话、记忆系统、定时任务、工具调用等能力。安装后需要配置 LLM API（如 Anthropic Claude、OpenAI GPT 等）。

参考文档：https://docs.openclaw.ai

## Step 8: 配置机器人身份

将 OpenClaw 配置模板复制到 workspace 并去掉 `.template` 后缀：

```bash
WORK_DIR="/root/.openclaw/workspace"
for tmpl in "$REPO_DIR/openclaw-templates/"*.template; do
    base=$(basename "$tmpl" .template)
    cp "$tmpl" "$WORK_DIR/$base"
done
```

然后编辑以下文件，填入你自己的信息：
- `SOUL.md` — 机器人性格和说话风格
- `USER.md` — 主人的基本信息（名字、时区、偏好）
- `IDENTITY.md` — 机器人名字和身份
- `TOOLS.md` — 硬件配置备忘
- `HEARTBEAT.md` — 心跳检查任务列表

## Step 9: 安装 systemd 服务

```bash
cp "$REPO_DIR/systemd/voice-assistant.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable voice-assistant
systemctl start voice-assistant
```

同时启动 OpenClaw：

```bash
openclaw gateway start
```

## Step 10: 验证

```bash
# 检查语音助手是否在运行
systemctl status voice-assistant

# 检查 OpenClaw 是否在运行
openclaw gateway status

# 查看语音助手日志
journalctl -u voice-assistant -f
```

对着麦克风说唤醒词（默认"五五零"），如果听到提示音并能对话，部署成功。

## Step 11: 注册声纹（可选）

```bash
cd "$WORK_DIR/voice-assistant"
python3 enroll_speaker.py 你的名字
# 按提示对着麦克风说几句话
```

注册后机器人能识别"谁在说话"。

---

## 故障排查

部署过程中遇到问题，参考 `docs/troubleshooting.md`。最常见的坑：

1. **VAD 不触发** → 检查 ALSA AGC 是否开启：`amixer -c 0 contents | grep -A2 'Auto Gain'`
2. **TTS 播放后录音异常** → USB 音频模块全双工问题，确认 voice_assistant.py 是最新版本
3. **舵机不动** → 检查 PWM export 和 enable：`cat /sys/class/pwm/pwmchip0/pwm0/enable`
4. **摄像头拍照失败** → MIPI 摄像头用 hobot_vio 的 libsrcampy，不是 V4L2
5. **模型下载慢** → 脚本已配置 hf-mirror.com 镜像，如果还慢可手动下载
