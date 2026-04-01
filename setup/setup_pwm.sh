#!/bin/bash
# PWM 舵机初始化
# RDK X5: pwmchip0/pwm0 = Yaw, pwmchip0/pwm1 = Pitch
set -e

GREEN='\033[0;32m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }

PWM_CHIP="/sys/class/pwm/pwmchip0"
PERIOD=20000000  # 20ms = 50Hz (标准舵机 PWM 频率)
CENTER=1500000   # 90° 中心位置

if [ ! -d "$PWM_CHIP" ]; then
    echo "未找到 pwmchip0，请确认硬件连接和设备树配置"
    exit 1
fi

for ch in 0 1; do
    PWM_DIR="$PWM_CHIP/pwm$ch"
    if [ ! -d "$PWM_DIR" ]; then
        info "导出 PWM 通道 $ch..."
        echo $ch > "$PWM_CHIP/export" 2>/dev/null || true
        sleep 0.5
    fi

    if [ -d "$PWM_DIR" ]; then
        info "配置 PWM$ch: period=${PERIOD}ns, duty=${CENTER}ns (90° 中心)"
        echo $PERIOD > "$PWM_DIR/period"
        echo $CENTER > "$PWM_DIR/duty_cycle"
        echo 1 > "$PWM_DIR/enable"
    fi
done

info "舵机初始化完成 — 两轴均归中 (90°)"
echo ""
echo "PWM 参数说明:"
echo "  Period: 20000000ns (50Hz)"
echo "  Duty range: 500000ns (0°) ~ 1500000ns (90°) ~ 2500000ns (180°)"
echo "  PWM0: Yaw (左右) — duty 减小=左, 增大=右"
echo "  PWM1: Pitch (上下) — duty 减小=低头, 增大=抬头"
echo "  安全行程: Yaw ±300000ns, Pitch ±200000ns (相对中心)"
