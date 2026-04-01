#!/usr/bin/env python3
"""鸡你太美 v3 - 严格节奏控制版
每个动作严格在分配的拍数内完成，避免时间漂移
"""
import time
import math
import os
import threading
import subprocess

PWM_YAW = "/sys/class/pwm/pwmchip0/pwm0"
PWM_PITCH = "/sys/class/pwm/pwmchip0/pwm1"
CENTER = 1500000
STEP = 100000

L = CENTER - STEP * 3
R = CENTER + STEP * 3
L2 = CENTER - STEP * 2
R2 = CENTER + STEP * 2
UP = CENTER - STEP * 2
DN = CENTER + STEP * 2
C = CENTER

BPM = 130.4
BEAT = 60.0 / BPM
MUSIC = "/root/.openclaw/workspace/media/jntm_real.wav"

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

def move2(y_start, y_end, p_start, p_end, dur, steps=15):
    """双轴同步移动，严格控制总时长"""
    dt = dur / steps
    for i in range(1, steps + 1):
        e = ease(i / steps)
        set_servo(PWM_YAW, y_start + (y_end - y_start) * e)
        set_servo(PWM_PITCH, p_start + (p_end - p_start) * e)
        time.sleep(dt)

def at_beat(t0, beat_num):
    """等到指定拍数的时刻"""
    target = t0 + beat_num * BEAT
    delay = target - time.monotonic()
    if delay > 0:
        time.sleep(delay)

def play_music():
    subprocess.run(["aplay", "-D", "plughw:0,0", MUSIC],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def choreography(t0):
    """完整编舞 - 每个动作严格卡拍"""
    
    # 拍0: 准备
    at_beat(t0, 0)
    move2(C, C, C, C, BEAT * 0.5, 10)
    
    # 拍3-10: 说唱开头 - 左右律动
    for i in range(4):
        b = 3 + i * 2
        at_beat(t0, b)
        ty = L2 if i % 2 == 0 else R2
        move2(C if i == 0 else (R2 if i % 2 == 0 else L2), ty, C, DN, BEAT * 0.8, 12)
        at_beat(t0, b + 1)
        move2(ty, C, DN, C, BEAT * 0.8, 12)
    
    # 拍11-22: 运球段 - 快速左右+点头
    for i in range(12):
        b = 11 + i * 0.5
        at_beat(t0, b)
        ty = L2 if i % 2 == 0 else R2
        tp = DN if i % 4 < 2 else C
        prev_y = R2 if i % 2 == 0 else L2
        prev_p = C if i % 4 < 2 else DN
        move2(prev_y if i > 0 else C, ty, prev_p if i > 0 else C, tp, BEAT * 0.4, 8)
    
    # 拍23-30: 波浪段
    wave_seq = [(L, DN), (L2, C), (C, UP), (R2, C), (R, DN), (R2, C), (C, UP), (L2, C)]
    for i, (y, p) in enumerate(wave_seq):
        b = 23 + i
        at_beat(t0, b)
        prev = wave_seq[i-1] if i > 0 else (C, C)
        move2(prev[0], y, prev[1], p, BEAT * 0.8, 12)
    
    # 拍31-34: 转身
    at_beat(t0, 31)
    move2(C, L, C, C, BEAT * 0.8, 10)
    at_beat(t0, 32)
    move2(L, R, C, C, BEAT * 1.5, 15)
    at_beat(t0, 34)
    move2(R, C, C, C, BEAT * 0.8, 10)
    
    # 拍35-42: 快速摇头
    for i in range(16):
        b = 35 + i * 0.5
        at_beat(t0, b)
        ty = L if i % 2 == 0 else R
        move2(R if i % 2 == 0 else L, ty, C, C, BEAT * 0.4, 8)
    
    # 拍43-50: 指人动作连击
    for i in range(4):
        b = 43 + i * 2
        at_beat(t0, b)
        move2(C, C, C, DN + STEP, BEAT * 0.6, 10)
        at_beat(t0, b + 1)
        move2(C, C, DN + STEP, C, BEAT * 0.6, 10)
    
    # 拍51-58: 波浪连击
    for i, (y, p) in enumerate(wave_seq):
        b = 51 + i
        at_beat(t0, b)
        prev = wave_seq[i-1] if i > 0 else (C, C)
        move2(prev[0], y, prev[1], p, BEAT * 0.8, 12)
    
    # 拍59-66: 疯狂左右甩
    for i in range(16):
        b = 59 + i * 0.5
        at_beat(t0, b)
        ty = L if i % 2 == 0 else R
        tp = DN if i % 4 < 2 else UP
        prev_y = R if i % 2 == 0 else L
        prev_p = UP if i % 4 < 2 else DN
        move2(prev_y if i > 0 else C, ty, prev_p if i > 0 else C, tp, BEAT * 0.35, 7)
    
    # 拍67-74: 再来一轮波浪
    for i, (y, p) in enumerate(wave_seq):
        b = 67 + i
        at_beat(t0, b)
        prev = wave_seq[i-1] if i > 0 else (C, C)
        move2(prev[0], y, prev[1], p, BEAT * 0.8, 12)
    
    # 拍75-82: 极速摇头
    for i in range(32):
        b = 75 + i * 0.25
        at_beat(t0, b)
        ty = L2 if i % 2 == 0 else R2
        move2(R2 if i % 2 == 0 else L2, ty, C, C, BEAT * 0.2, 5)
    
    # 拍83-90: 大幅横扫
    for i in range(8):
        b = 83 + i
        at_beat(t0, b)
        ty = L if i % 2 == 0 else R
        move2(R if i % 2 == 0 else L, ty, C, C, BEAT * 0.8, 12)
    
    # 拍91-98: 上下起伏
    for i in range(8):
        b = 91 + i
        at_beat(t0, b)
        tp = DN if i % 2 == 0 else UP
        move2(C, C, UP if i % 2 == 0 else DN, tp, BEAT * 0.8, 12)
    
    # 拍99-106: 组合动作 - 左右+上下
    for i in range(8):
        b = 99 + i
        at_beat(t0, b)
        ty = L if i % 2 == 0 else R
        tp = DN if i % 2 == 0 else UP
        prev_y = R if i % 2 == 0 else L
        prev_p = UP if i % 2 == 0 else DN
        move2(prev_y if i > 0 else C, ty, prev_p if i > 0 else C, tp, BEAT * 0.8, 12)
    
    # 拍107-114: 最后波浪
    for i, (y, p) in enumerate(wave_seq):
        b = 107 + i
        at_beat(t0, b)
        prev = wave_seq[i-1] if i > 0 else (C, C)
        move2(prev[0], y, prev[1], p, BEAT * 0.8, 12)
    
    # 拍115-120: 慢速大幅摇摆
    at_beat(t0, 115)
    move2(C, L, C, C, BEAT * 1.5, 15)
    at_beat(t0, 117)
    move2(L, R, C, C, BEAT * 2.0, 18)
    at_beat(t0, 120)
    move2(R, C, C, C, BEAT * 1.5, 15)
    
    # 拍122-128: 鞠躬结束
    at_beat(t0, 122)
    move2(C, C, C, DN + STEP * 2, BEAT * 2.0, 20)
    at_beat(t0, 126)
    move2(C, C, DN + STEP * 2, C, BEAT * 2.0, 20)
    
    set_servo(PWM_YAW, C)
    set_servo(PWM_PITCH, C)

def main():
    init_pwm()
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    
    print("🐔 鸡你太美 v3 - 严格节奏版")
    time.sleep(0.5)
    
    audio_thread = threading.Thread(target=play_music, daemon=True)
    t0 = time.monotonic()
    audio_thread.start()
    
    print("🎵 开始表演！")
    choreography(t0)
    
    audio_thread.join(timeout=5)
    
    set_servo(PWM_YAW, CENTER)
    set_servo(PWM_PITCH, CENTER)
    
    print("✨ 表演结束！")

if __name__ == "__main__":
    main()
