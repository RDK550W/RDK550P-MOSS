#!/bin/bash
# RDK550P-MOSS 一键安装脚本
# 适用于 RDK X5 (Ubuntu 22.04, aarch64)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VOICE_DIR="$PROJECT_DIR/voice-assistant"
SCRIPTS_DIR="$PROJECT_DIR/scripts"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- 检查运行环境 ---
echo "========================================="
echo "  RDK550P-MOSS 安装脚本"
echo "========================================="
echo ""

if [ "$(uname -m)" != "aarch64" ]; then
    warn "当前架构不是 aarch64，此脚本为 RDK X5 设计"
    read -p "是否继续？(y/N) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

if [ "$EUID" -ne 0 ]; then
    error "请使用 sudo 运行此脚本"
fi

# --- 1. 系统依赖 ---
info "安装系统依赖..."
apt-get update
apt-get install -y \
    alsa-utils \
    ffmpeg \
    bc \
    python3-pip \
    python3-dev \
    git \
    wget \
    curl

# --- 2. Python 依赖 ---
info "安装 Python 依赖..."
pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r "$SCRIPT_DIR/requirements.txt"

# --- 3. 下载 AI 模型 ---
info "下载 AI 模型 (~2.2GB)..."
bash "$SCRIPT_DIR/download_models.sh"

# --- 4. 配置 ALSA ---
info "配置 ALSA 音频（USB 麦克风+扬声器一体模块）..."
bash "$SCRIPT_DIR/setup_alsa.sh"

# --- 5. 配置 PWM ---
info "配置 PWM 舵机..."
bash "$SCRIPT_DIR/setup_pwm.sh"

# --- 6. 创建工作目录并部署文件 ---
info "部署文件到 OpenClaw workspace..."
WORK_DIR="/root/.openclaw/workspace"
mkdir -p "$WORK_DIR/voice-assistant/models"
mkdir -p "$WORK_DIR/voice-assistant/sounds"
mkdir -p "$WORK_DIR/scripts"
mkdir -p "$WORK_DIR/media"
mkdir -p "$WORK_DIR/memory"

# 复制语音助手
cp "$VOICE_DIR"/*.py "$WORK_DIR/voice-assistant/"
cp "$VOICE_DIR/start.sh" "$WORK_DIR/voice-assistant/"
cp "$VOICE_DIR/sounds/"* "$WORK_DIR/voice-assistant/sounds/" 2>/dev/null || true

# 复制工具脚本
cp "$SCRIPTS_DIR"/*.py "$WORK_DIR/scripts/"

# 链接模型（避免重复占用空间）
MODEL_SRC="$VOICE_DIR/models"
MODEL_DST="$WORK_DIR/voice-assistant/models"
if [ -d "$MODEL_SRC/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17" ]; then
    ln -sf "$MODEL_SRC/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17" "$MODEL_DST/"
fi
for f in silero_vad.onnx 3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx; do
    [ -f "$MODEL_SRC/$f" ] && ln -sf "$MODEL_SRC/$f" "$MODEL_DST/$f"
done
if [ -d "$MODEL_SRC/sherpa-onnx-pyannote-segmentation-3-0" ]; then
    ln -sf "$MODEL_SRC/sherpa-onnx-pyannote-segmentation-3-0" "$MODEL_DST/"
fi

# 创建空的声纹数据库
echo '{}' > "$WORK_DIR/voice-assistant/speaker_db.json"
echo '{}' > "$WORK_DIR/voice-assistant/unknown_speakers.json"

# --- 7. 复制 OpenClaw 配置模板 ---
info "部署 OpenClaw 配置模板..."
TEMPLATES_DIR="$PROJECT_DIR/openclaw-templates"
if [ -d "$TEMPLATES_DIR" ]; then
    for tmpl in "$TEMPLATES_DIR"/*.template; do
        base=$(basename "$tmpl" .template)
        if [ ! -f "$WORK_DIR/$base" ]; then
            cp "$tmpl" "$WORK_DIR/$base"
            info "  已创建 $base"
        else
            warn "  $base 已存在，跳过"
        fi
    done
fi

# --- 8. 安装 systemd 服务 ---
info "安装 systemd 服务..."
cp "$PROJECT_DIR/systemd/voice-assistant.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable voice-assistant
info "  voice-assistant.service 已安装并启用"

# --- 9. 持久化 ALSA 设置 ---
info "持久化 ALSA 设置..."
alsactl store 2>/dev/null || warn "alsactl store 失败，ALSA 设置可能重启后丢失"

# --- 完成 ---
echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "接下来："
echo "  1. 安装 OpenClaw:  curl -fsSL https://get.openclaw.ai | bash"
echo "  2. 配置 OpenClaw:  openclaw init"
echo "  3. 编辑身份文件:   vim ~/.openclaw/workspace/SOUL.md"
echo "  4. 启动语音助手:   sudo systemctl start voice-assistant"
echo "  5. 注册声纹:       cd ~/.openclaw/workspace/voice-assistant && python3 enroll_speaker.py 你的名字"
echo ""
echo "查看日志:  journalctl -u voice-assistant -f"
echo ""
