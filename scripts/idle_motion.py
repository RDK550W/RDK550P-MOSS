#!/usr/bin/env python3
"""闲时活动 - 随机小动作，让机器人看起来有生命感"""
import time
import math
import os
import random

PWM_YAW = "/sys/class/pwm/pwmchip0/pwm0"
PWM_PITCH = "/sys/class/pwm/pwmchip0/pwm1"
CENTER = 1500000
YAW_RANGE = 300000
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

def move(pwm_path, start, end, duration=0.3, steps=18):
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        pos = start + (end - start) * ease(t)
        set_servo(pwm_path, pos)
        time.sleep(dt)

def get_pos(pwm_path):
    with open(f"{pwm_path}/duty_cycle") as f:
        return int(f.read().strip())

# ===== 闲时动作库 =====

def look_around():
    """缓缓环顾四周"""
    cy, cp = get_pos(PWM_YAW), get_pos(PWM_PITCH)
    # 随机选一个方向看
    targets = [
        (CENTER - YAW_RANGE * 0.7, CENTER),                # 看左
        (CENTER + YAW_RANGE * 0.7, CENTER),                # 看右
        (CENTER - YAW_RANGE * 0.5, CENTER + PITCH_RANGE * 0.4),  # 左上方
        (CENTER + YAW_RANGE * 0.5, CENTER + PITCH_RANGE * 0.4),  # 右上方
        (CENTER, CENTER - PITCH_RANGE * 0.5),              # 低头看桌面
        (CENTER - YAW_RANGE * 0.8, CENTER - PITCH_RANGE * 0.3),  # 左下
        (CENTER + YAW_RANGE * 0.8, CENTER - PITCH_RANGE * 0.3),  # 右下
    ]
    ty, tp = random.choice(targets)
    ty, tp = int(ty), int(tp)
    
    # 缓缓转过去
    move(PWM_YAW, cy, ty, duration=0.6, steps=22)
    move(PWM_PITCH, cp, tp, duration=0.4, steps=18)
    # 停留看一会
    time.sleep(random.uniform(0.8, 2.0))
    # 回中
    move(PWM_YAW, ty, CENTER, duration=0.5, steps=20)
    move(PWM_PITCH, tp, CENTER, duration=0.3, steps=15)

def curious_tilt():
    """好奇地歪头"""
    cy = get_pos(PWM_YAW)
    direction = random.choice([-1, 1])
    amp = random.randint(100000, 200000)
    target = CENTER + direction * amp
    move(PWM_YAW, cy, target, duration=0.25, steps=15)
    # 小幅点头
    cp = get_pos(PWM_PITCH)
    move(PWM_PITCH, cp, cp - 80000, duration=0.12, steps=10)
    move(PWM_PITCH, cp - 80000, cp, duration=0.12, steps=10)
    time.sleep(random.uniform(0.3, 0.8))
    move(PWM_YAW, target, CENTER, duration=0.3, steps=15)

def gentle_nod():
    """轻轻点头，像在思考"""
    cp = get_pos(PWM_PITCH)
    for _ in range(random.randint(1, 3)):
        amp = random.randint(60000, 120000)
        move(PWM_PITCH, cp, cp - amp, duration=0.15, steps=12)
        move(PWM_PITCH, cp - amp, cp, duration=0.15, steps=12)
        time.sleep(0.05)

def slow_stretch():
    """伸懒腰 - 先仰头再左右慢摆"""
    cy, cp = get_pos(PWM_YAW), get_pos(PWM_PITCH)
    # 仰头
    move(PWM_PITCH, cp, CENTER + PITCH_RANGE * 0.6, duration=0.4, steps=18)
    time.sleep(0.3)
    # 慢慢左右
    move(PWM_YAW, cy, CENTER - YAW_RANGE * 0.5, duration=0.5, steps=20)
    move(PWM_YAW, CENTER - YAW_RANGE * 0.5, CENTER + YAW_RANGE * 0.5, duration=0.8, steps=25)
    move(PWM_YAW, CENTER + YAW_RANGE * 0.5, CENTER, duration=0.5, steps=20)
    # 回正
    move(PWM_PITCH, CENTER + PITCH_RANGE * 0.6, CENTER, duration=0.3, steps=15)

def idle_sway():
    """轻微晃动，像在听音乐"""
    amp = random.randint(80000, 150000)
    for _ in range(random.randint(2, 4)):
        move(PWM_YAW, CENTER - amp, CENTER + amp, duration=0.35, steps=18)
        move(PWM_YAW, CENTER + amp, CENTER - amp, duration=0.35, steps=18)
    move(PWM_YAW, get_pos(PWM_YAW), CENTER, duration=0.2, steps=12)

# ===== 主入口 =====

MOTIONS = [look_around, curious_tilt, gentle_nod, slow_stretch, idle_sway]

def do_random_motion(count=None):
    """执行随机动作，count=None 时随机 1~3 个"""
    init_pwm()
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    time.sleep(0.2)
    
    if count is None:
        count = random.randint(1, 3)
    
    chosen = random.sample(MOTIONS, min(count, len(MOTIONS)))
    for motion in chosen:
        motion()
        time.sleep(random.uniform(0.2, 0.5))
    
    # 确保回中
    move(PWM_YAW, get_pos(PWM_YAW), CENTER, duration=0.3, steps=15)
    move(PWM_PITCH, get_pos(PWM_PITCH), CENTER, duration=0.2, steps=12)

if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else None
    do_random_motion(count)
