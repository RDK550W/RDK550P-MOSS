#!/bin/bash
# ALSA 音频配置 — USB 麦克风
# 关键：必须开启 AGC，否则 VAD 无法检测语音
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 查找 USB 音频设备
USB_CARD=$(arecord -l 2>/dev/null | grep -i "usb\|uac\|jieli" | head -1 | sed 's/card \([0-9]*\):.*/\1/')

if [ -z "$USB_CARD" ]; then
    error "未检测到 USB 音频设备，请确认已插入 USB 麦克风"
    exit 1
fi

info "检测到 USB 音频设备: card $USB_CARD"

# 开启 AGC（自动增益控制）— 这是最关键的设置
info "开启 Auto Gain Control..."
amixer -c "$USB_CARD" set 'Auto Gain Control' on 2>/dev/null && \
    info "  AGC 已开启" || \
    warn "  未找到 AGC 控制项（不同型号的 USB 麦克风控制项可能不同）"

# 麦克风增益拉满
info "设置麦克风增益..."
amixer -c "$USB_CARD" set 'Mic' 147 2>/dev/null && \
    info "  Mic 增益已设为 147" || \
    warn "  未找到 Mic 控制项"

# 显示当前 ALSA 设置
info "当前 ALSA 设置:"
amixer -c "$USB_CARD" contents 2>/dev/null | grep -A2 "'Auto Gain\|'Mic'" || true

# 持久化
info "持久化 ALSA 设置..."
alsactl store 2>/dev/null && \
    info "  已保存（alsactl store）" || \
    warn "  alsactl store 失败，建议在 systemd service 中添加 ExecStartPre 设置"

echo ""
info "ALSA 配置完成"
echo ""
echo "如果重启后设置丢失，可在 voice-assistant.service 中添加："
echo "  ExecStartPre=/usr/bin/amixer -c $USB_CARD set 'Auto Gain Control' on"
echo "  ExecStartPre=/usr/bin/amixer -c $USB_CARD set 'Mic' 147"
