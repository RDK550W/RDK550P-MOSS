#!/usr/bin/env python3
"""Funky Robot Dance - 节奏感强的新舞蹈，融合抖动、画圈、甩头"""
import time
import math
import os

PWM_YAW = "/sys/class/pwm/pwmchip0/pwm0"
PWM_PITCH = "/sys/class/pwm/pwmchip0/pwm1"
CENTER = 1500000
YAW_RANGE = 300000   # 安全行程
PITCH_RANGE = 200000

def init_pwm():
    for ch in (0, 1):
        base = f"/sys/class/pwm/pwmchip0/pwm{ch}"
        if not os.path.isdir(base):
            with open("/sys/class/pwm/pwmchip0/export", "w") as f:
                f.write(str(ch))
        for name, val in [("period", "20000000"), ("duty_cycle", str(CENTER)), ("enable", "1")]:
            try:
                with open(f"{base}/{name}", "w") as f:
                    f.write(val)
            except OSError:
                pass

def set_servo(pwm_path, duty):
    duty = max(500000, min(2500000, int(duty)))
    with open(f"{pwm_path}/duty_cycle", "w") as f:
        f.write(str(duty))

def ease(t):
    return (1 - math.cos(t * math.pi)) / 2

def move(pwm_path, start, end, duration=0.2, steps=15):
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        pos = start + (end - start) * ease(t)
        set_servo(pwm_path, pos)
        time.sleep(dt)

def move_both(yaw_start, yaw_end, pitch_start, pitch_end, duration=0.2, steps=15):
    """同时移动两个舵机"""
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        e = ease(t)
        set_servo(PWM_YAW, yaw_start + (yaw_end - yaw_start) * e)
        set_servo(PWM_PITCH, pitch_start + (pitch_end - pitch_start) * e)
        time.sleep(dt)

def get_pos(pwm_path):
    """读取当前 duty_cycle"""
    with open(f"{pwm_path}/duty_cycle") as f:
        return int(f.read().strip())

# ===== 动作库 =====

def head_circle(radius_yaw=200000, radius_pitch=150000, duration=1.0, steps=40):
    """画圈 - 头部绕一个椭圆"""
    dt = duration / steps
    cy, cp = get_pos(PWM_YAW), get_pos(PWM_PITCH)
    for i in range(steps + 1):
        angle = 2 * math.pi * i / steps
        yaw = cy + radius_yaw * math.sin(angle)
        pitch = cp + radius_pitch * math.cos(angle)
        set_servo(PWM_YAW, yaw)
        set_servo(PWM_PITCH, pitch)
        time.sleep(dt)

def head_figure8(radius_yaw=200000, radius_pitch=120000, duration=1.5, steps=50):
    """8字摇摆"""
    dt = duration / steps
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * t
        yaw = CENTER + radius_yaw * math.sin(angle)
        pitch = CENTER + radius_pitch * math.sin(2 * angle)
        set_servo(PWM_YAW, yaw)
        set_servo(PWM_PITCH, pitch)
        time.sleep(dt)

def quick_tilt(direction=1, amp=150000, duration=0.12, steps=12):
    """快速歪头 - direction: 1=右歪, -1=左歪（用 yaw 模拟）"""
    cy = get_pos(PWM_YAW)
    target = cy + direction * amp
    move(PWM_YAW, cy, target, duration, steps)
    time.sleep(0.03)
    move(PWM_YAW, target, cy, duration, steps)

def shimmy(times=4, amp=120000, period=0.12):
    """快速左右抖动"""
    for i in range(times):
        d = 1 if i % 2 == 0 else -1
        move(PWM_YAW, CENTER - d * amp, CENTER + d * amp, duration=period, steps=10)
    move(PWM_YAW, get_pos(PWM_YAW), CENTER, duration=0.1, steps=8)

def slow_scan(duration=0.8):
    """慢速扫视 - 像在环顾四周"""
    move(PWM_YAW, CENTER, CENTER - YAW_RANGE, duration=duration * 0.4, steps=20)
    time.sleep(0.1)
    move(PWM_YAW, CENTER - YAW_RANGE, CENTER + YAW_RANGE, duration=duration * 0.6, steps=25)
    time.sleep(0.1)
    move(PWM_YAW, CENTER + YAW_RANGE, CENTER, duration=duration * 0.3, steps=15)

def double_take():
    """双重回头 - 假装看到什么吓一跳"""
    # 先慢慢转右
    move(PWM_YAW, CENTER, CENTER + 200000, duration=0.3, steps=15)
    time.sleep(0.15)
    # 快速甩回左
    move(PWM_YAW, CENTER + 200000, CENTER - 250000, duration=0.1, steps=12)
    time.sleep(0.05)
    # 快速甩回右
    move(PWM_YAW, CENTER - 250000, CENTER + 200000, duration=0.1, steps=12)
    # 停顿（震惊状）
    time.sleep(0.2)
    # 慢慢回中
    move(PWM_YAW, CENTER + 200000, CENTER, duration=0.25, steps=15)

def groove_nod(times=3, speed=1.0):
    """律动点头 - 带节奏感的点头，幅度递减"""
    for i in range(times):
        amp = int(PITCH_RANGE * (1.0 - i * 0.2))
        d = 0.12 / speed
        move(PWM_PITCH, CENTER, CENTER - amp, duration=d, steps=12)
        move(PWM_PITCH, CENTER - amp, CENTER, duration=d * 0.7, steps=10)
        time.sleep(0.02)

def sway_groove(cycles=2, speed=1.0):
    """摇摆律动 - yaw 大幅摆 + pitch 小律动同步"""
    amp_y = 250000
    amp_p = 100000
    period = 0.5 / speed
    steps = 20
    for c in range(cycles):
        d = 1 if c % 2 == 0 else -1
        dt = period / steps
        for i in range(1, steps + 1):
            t = i / steps
            e = ease(t)
            yaw = CENTER + d * amp_y * (2 * e - 1) if c > 0 else CENTER + d * amp_y * e
            pitch = CENTER + amp_p * math.sin(t * math.pi * 2)
            set_servo(PWM_YAW, yaw)
            set_servo(PWM_PITCH, pitch)
            time.sleep(dt)

def dramatic_bow():
    """戏剧性鞠躬"""
    # 先仰头
    move(PWM_PITCH, CENTER, CENTER + PITCH_RANGE, duration=0.2, steps=15)
    time.sleep(0.15)
    # 快速低头鞠躬
    move(PWM_PITCH, CENTER + PITCH_RANGE, CENTER - PITCH_RANGE, duration=0.18, steps=15)
    time.sleep(0.3)
    # 优雅回正
    move(PWM_PITCH, CENTER - PITCH_RANGE, CENTER, duration=0.3, steps=18)

# ===== 编舞 =====

def dance():
    init_pwm()
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    time.sleep(0.3)

    print("Funky Dance Start!")

    # === 第一段：开场 - 环顾+歪头（好奇地看周围） ===
    slow_scan(duration=0.8)
    time.sleep(0.1)
    quick_tilt(1)
    time.sleep(0.1)
    quick_tilt(-1)
    time.sleep(0.2)

    # === 第二段：律动 - 点头+摇摆（找到节奏了） ===
    groove_nod(times=4, speed=1.2)
    time.sleep(0.1)
    sway_groove(cycles=3, speed=1.3)
    time.sleep(0.1)

    # === 第三段：加速 - 快速抖动+画圈（嗨起来） ===
    shimmy(times=6, amp=150000, period=0.1)
    time.sleep(0.1)
    head_circle(radius_yaw=220000, radius_pitch=150000, duration=0.8, steps=35)
    time.sleep(0.05)
    head_circle(radius_yaw=180000, radius_pitch=120000, duration=0.6, steps=30)
    time.sleep(0.1)

    # === 第四段：高潮 - 8字+甩头（全力输出） ===
    head_figure8(radius_yaw=250000, radius_pitch=150000, duration=1.2, steps=45)
    time.sleep(0.1)
    double_take()
    time.sleep(0.1)
    shimmy(times=8, amp=180000, period=0.08)
    time.sleep(0.1)

    # === 第五段：收尾 - 慢摇+鞠躬 ===
    sway_groove(cycles=2, speed=0.8)
    time.sleep(0.2)
    dramatic_bow()
    time.sleep(0.1)

    # 回中
    move_both(get_pos(PWM_YAW), CENTER, get_pos(PWM_PITCH), CENTER, duration=0.3, steps=18)
    time.sleep(0.2)

    print("Funky Dance Done!")

if __name__ == "__main__":
    dance()
