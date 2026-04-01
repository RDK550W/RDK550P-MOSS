#!/usr/bin/env python3
"""舵机跳舞脚本 v4 - Python 版，高精度缓动控制"""
import time
import math
import os

PWM_YAW = "/sys/class/pwm/pwmchip0/pwm0"
PWM_PITCH = "/sys/class/pwm/pwmchip0/pwm1"
CENTER = 1500000
STEP = 100000

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
    with open(f"{pwm_path}/duty_cycle", "w") as f:
        f.write(str(int(duty)))

def ease_in_out(t):
    """Smooth ease-in-out using cosine: 0->1 smoothly"""
    return (1 - math.cos(t * math.pi)) / 2

def move_eased(pwm_path, start, end, duration=0.3, steps=20):
    """
    平滑缓动移动
    duration: 总耗时(秒)
    steps: 插值步数（越多越丝滑）
    """
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        eased = ease_in_out(t)
        pos = start + (end - start) * eased
        set_servo(pwm_path, pos)
        time.sleep(dt)

def nod(speed=1.0):
    """点头动作"""
    d = 0.15 / speed
    move_eased(PWM_PITCH, CENTER, CENTER - STEP * 2, duration=d, steps=12)
    move_eased(PWM_PITCH, CENTER - STEP * 2, CENTER, duration=d, steps=12)

def bow():
    """鞠躬"""
    move_eased(PWM_PITCH, CENTER, CENTER + STEP * 2, duration=0.25, steps=15)
    time.sleep(0.1)
    move_eased(PWM_PITCH, CENTER + STEP * 2, CENTER - STEP, duration=0.3, steps=18)
    move_eased(PWM_PITCH, CENTER - STEP, CENTER, duration=0.2, steps=12)

def dance():
    init_pwm()
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    time.sleep(0.3)

    yaw_left = CENTER - STEP * 3
    yaw_right = CENTER + STEP * 3

    print("开始跳舞 (v4 Python 缓动版)")

    # 3 轮左右摇摆 + 点头
    for round_i in range(3):
        speed = 1.4 + round_i * 0.2  # 基础更快，每轮加速

        # 向左
        move_eased(PWM_YAW, CENTER, yaw_left, duration=0.25 / speed, steps=15)
        nod(speed)

        # 向右
        move_eased(PWM_YAW, yaw_left, yaw_right, duration=0.4 / speed, steps=25)
        nod(speed)

        # 回中
        move_eased(PWM_YAW, yaw_right, CENTER, duration=0.25 / speed, steps=15)
        time.sleep(0.03)

    # 鞠躬两下
    for _ in range(2):
        bow()
        time.sleep(0.05)

    # 回中位
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    print("舞蹈完成!")

if __name__ == "__main__":
    dance()
