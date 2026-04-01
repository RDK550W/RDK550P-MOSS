# RDK X5 PWM 舵机控制：从原理到云台机器人

> 完整实战教程 | Linux PWM 驱动 + 舵机控制原理 + 云台动作编程
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

在 RDK X5 上用 PWM 控制舵机，实现一个能"摇头""点头""跳舞"的云台机器人：
- 理解 PWM 信号与舵机角度的关系
- 掌握 Linux sysfs PWM 接口
- 实现平滑、安全的舵机运动控制
- 编写跳舞、巡视等动作组合

**适合谁？**
- 刚接触嵌入式舵机控制的开发者
- 想在 RDK X5 上做云台/摇头机器人的同学
- 需要了解 Linux PWM sysfs 接口的工程师

---

## 目录

1. [硬件准备](#1-硬件准备)
2. [舵机基础知识](#2-舵机基础知识)
3. [Linux PWM sysfs 接口](#3-linux-pwm-sysfs-接口)
4. [RDK X5 的 PWM 引脚](#4-rdk-x5-的-pwm-引脚)
5. [基本控制代码](#5-基本控制代码)
   - 5.1 初始化 PWM
   - 5.2 设置角度
   - 5.3 平滑移动（关键！）
6. [云台控制实战](#6-云台控制实战)
   - 6.1 Pan-Tilt 云台结构
   - 6.2 跳舞动作编程
   - 6.3 巡视模式
7. [Shell 脚本实现](#7-shell-脚本实现)
8. [Python 实现](#8-python-实现)
9. [安全注意事项](#9-安全注意事项)
10. [常见问题](#10-常见问题)

---

## 1. 硬件准备

| 硬件 | 说明 |
|------|------|
| RDK X5 开发板 | 带 40pin GPIO 接口 |
| 数字舵机 × 2 | 推荐 SG90 / MG90S（小型，适合桌面云台） |
| 云台支架 | 2 轴 Pan-Tilt 支架（淘宝搜"SG90 云台"） |
| 杜邦线若干 | 母对母，用于连接 GPIO |
| 5V 电源 | 舵机供电（可用 RDK X5 的 5V 引脚或外部电源） |

**接线方式：**

舵机有三根线：
- **棕色/黑色**：GND（接 RDK X5 的 GND 引脚）
- **红色**：VCC 5V（接 RDK X5 的 5V 引脚或外部 5V）
- **橙色/黄色**：信号线（接 PWM 引脚）

> **供电警告**：如果两个舵机同时大幅度快速转动，瞬间电流可能达到 1A 以上。建议使用外部 5V 电源为舵机供电，只共地即可。直接从 RDK X5 的 5V 引脚取电可能导致板子电压降低甚至重启。

---

## 2. 舵机基础知识

### PWM 控制原理

舵机通过 PWM（脉宽调制）信号控制角度：

```
  PWM 周期 = 20ms (50Hz)
  ┌──┐                    ┌──┐
  │  │                    │  │
──┘  └────────────────────┘  └───

  ←──→
  脉宽（duty cycle）决定角度
```

| 脉宽 | 角度 |
|------|------|
| 0.5ms | 0° |
| 1.0ms | 45° |
| 1.5ms | 90°（中位） |
| 2.0ms | 135° |
| 2.5ms | 180° |

在 Linux sysfs 中，时间单位是**纳秒（ns）**：

| 参数 | 纳秒值 | 说明 |
|------|--------|------|
| period | 20,000,000 ns | PWM 周期（50Hz） |
| duty_cycle (0°) | 500,000 ns | 0.5ms |
| duty_cycle (90°) | 1,500,000 ns | 1.5ms |
| duty_cycle (180°) | 2,500,000 ns | 2.5ms |

### 角度与 duty_cycle 的换算

```
duty_cycle(ns) = 500000 + (angle / 180) × 2000000
```

例如：
- 45° → 500000 + (45/180) × 2000000 = 1,000,000 ns
- 90° → 500000 + (90/180) × 2000000 = 1,500,000 ns

---

## 3. Linux PWM sysfs 接口

Linux 提供了通用的 sysfs 接口来控制 PWM，不需要写内核驱动。

### 目录结构

```
/sys/class/pwm/pwmchipN/
├── export          # 导出 PWM 通道
├── unexport        # 取消导出
└── pwmM/           # 导出后出现
    ├── period      # 周期（ns）
    ├── duty_cycle  # 占空比（ns）
    ├── enable      # 1=启用, 0=禁用
    └── polarity    # 极性
```

### 基本操作流程

```bash
# 1. 导出 PWM 通道（以 pwmchip0 的通道 0 为例）
echo 0 > /sys/class/pwm/pwmchip0/export

# 2. 设置周期为 20ms（50Hz）
echo 20000000 > /sys/class/pwm/pwmchip0/pwm0/period

# 3. 设置占空比（1.5ms = 90° 中位）
echo 1500000 > /sys/class/pwm/pwmchip0/pwm0/duty_cycle

# 4. 启用 PWM 输出
echo 1 > /sys/class/pwm/pwmchip0/pwm0/enable
```

就这么简单。一行 `echo` 命令就能让舵机转到指定角度。

---

## 4. RDK X5 的 PWM 引脚

RDK X5 的 40pin 接口提供了 PWM 输出：

| PWM 控制器 | 通道 | 40pin 引脚 | 用途（本教程） |
|------------|------|------------|---------------|
| pwmchip0/pwm0 | ch0 | Pin 32 (LSIO_PWM_OUT6) | Yaw（左右旋转） |
| pwmchip0/pwm1 | ch1 | Pin 33 (LSIO_PWM_OUT7) | Pitch（上下俯仰） |

查看系统中可用的 PWM 控制器：

```bash
ls /sys/class/pwm/
# pwmchip0  pwmchip2  ...
```

查看控制器信息：

```bash
cat /sys/class/pwm/pwmchip0/npwm   # 通道数
# 2
```

---

## 5. 基本控制代码

### 5.1 初始化 PWM

```bash
#!/bin/bash
PWM_PATH=/sys/class/pwm/pwmchip0
CENTER=1500000  # 90° 中位

# 导出两个通道
for ch in 0 1; do
    if [ ! -d ${PWM_PATH}/pwm${ch} ]; then
        echo $ch > ${PWM_PATH}/export 2>/dev/null
    fi
    echo 20000000 > ${PWM_PATH}/pwm${ch}/period
    echo $CENTER > ${PWM_PATH}/pwm${ch}/duty_cycle
    echo 1 > ${PWM_PATH}/pwm${ch}/enable
done

echo "PWM 初始化完成，舵机已回中位"
```

### 5.2 设置角度

```bash
# 设置舵机角度
# 用法：set_angle <pwm_path> <duty_ns>
set_servo() {
    echo "$2" > "$1/duty_cycle"
}

# 示例：Yaw 转到 45°（duty = 1000000ns）
set_servo /sys/class/pwm/pwmchip0/pwm0 1000000

# 示例：Pitch 抬头到 120°（duty = 1833333ns）
set_servo /sys/class/pwm/pwmchip0/pwm1 1833333
```

### 5.3 平滑移动（关键！）

**直接跳转到目标角度是危险的！** 原因：
1. 舵机瞬间启动，电流冲击大（可能导致板子重启）
2. 机械冲击大，容易损坏舵机齿轮或云台结构
3. 噪音大，体验差

**正确做法：分步渐进移动**

```bash
# 渐进移动：从 from 到 to，分 steps 步，每步间隔 delay 秒
move_to() {
    local pwm=$1
    local from=$2
    local to=$3
    local steps=$4
    local delay=$5
    
    for i in $(seq 1 $steps); do
        # 线性插值计算当前位置
        local pos=$(( from + (to - from) * i / steps ))
        echo "$pos" > "$pwm/duty_cycle"
        sleep $delay
    done
}

# 示例：Yaw 从中位平滑转到左边
# 每步 100000ns，sleep 0.08s，共 3 步
move_to /sys/class/pwm/pwmchip0/pwm0 1500000 1200000 3 0.08
```

> **经验值**：每步变化 100000ns（约 9°），间隔 0.08 秒，是一个比较安全和自然的速度。太快会电流冲击，太慢会显得呆板。

> **踩坑提醒**：RDK X5 系统默认没装 `bc` 计算器。Shell 脚本里不要用 `bc` 做浮点运算。用 `$(( ))` 做整数运算就够了，sleep 的小数直接写就行（如 `sleep 0.08`）。

---

## 6. 云台控制实战

### 6.1 Pan-Tilt 云台结构

```
       ┌─────────┐
       │  Camera  │  ← 摄像头/头部
       └────┬────┘
            │
       ┌────┴────┐
       │  Pitch  │  ← 上下俯仰（pwm1）
       │  Servo  │
       └────┬────┘
            │
       ┌────┴────┐
       │   Yaw   │  ← 左右旋转（pwm0）
       │  Servo  │
       └────┬────┘
            │
       ═════╧═════  ← 底座/桌面
```

**方向约定（本教程使用）：**
- duty_cycle 减小 → Yaw 向左 / Pitch 向下（低头）
- duty_cycle 增大 → Yaw 向右 / Pitch 向上（抬头）

> 不同舵机安装方向可能导致方向相反，请根据实际情况调整。

### 6.2 跳舞动作编程

跳舞的本质是把基本动作（摇头、点头、鞠躬）组合成节奏感强的序列。

**基本动作库：**

```bash
STEP=100000
CENTER=1500000

# 向左摇
shake_left() {
    move_to $PWM_YAW $CENTER $((CENTER - STEP*3)) 3 0.08
}

# 向右摇
shake_right() {
    move_to $PWM_YAW $((CENTER - STEP*3)) $((CENTER + STEP*3)) 6 0.08
}

# 点头
nod() {
    move_to $PWM_PITCH $CENTER $((CENTER - STEP*2)) 2 0.1
    move_to $PWM_PITCH $((CENTER - STEP*2)) $CENTER 2 0.1
}

# 鞠躬
bow() {
    move_to $PWM_PITCH $CENTER $((CENTER + STEP*2)) 3 0.08
    move_to $PWM_PITCH $((CENTER + STEP*2)) $((CENTER - STEP*2)) 4 0.08
    move_to $PWM_PITCH $((CENTER - STEP*2)) $CENTER 3 0.08
}
```

**组合成完整舞蹈：**

```bash
# 3 轮左右摇摆 + 点头
for round in 1 2 3; do
    shake_left
    nod
    shake_right
    nod
    # 回中
    move_to $PWM_YAW $((CENTER + STEP*3)) $CENTER 3 0.08
    sleep 0.2
done

# 最后鞠躬两下
bow
sleep 0.15
bow
```

### 6.3 巡视模式

让云台自动左右扫描，适合配合摄像头做监控：

```bash
# 巡视：左右往复扫描
LEFT_LIMIT=$((CENTER - STEP*4))    # 左极限
RIGHT_LIMIT=$((CENTER + STEP*4))   # 右极限
SCAN_STEPS=8
SCAN_DELAY=0.1

while true; do
    # 向右扫
    move_to $PWM_YAW $LEFT_LIMIT $RIGHT_LIMIT $SCAN_STEPS $SCAN_DELAY
    sleep 0.5
    # 向左扫
    move_to $PWM_YAW $RIGHT_LIMIT $LEFT_LIMIT $SCAN_STEPS $SCAN_DELAY
    sleep 0.5
done
```

---

## 7. Shell 脚本实现

完整的跳舞脚本：

```bash
#!/bin/bash
# RDK X5 舵机跳舞脚本
# 用法：bash dance.sh

PWM_YAW=/sys/class/pwm/pwmchip0/pwm0
PWM_PITCH=/sys/class/pwm/pwmchip0/pwm1

CENTER=1500000
STEP=100000

# ── 初始化 ──────────────────────────────
for ch in 0 1; do
    if [ ! -d /sys/class/pwm/pwmchip0/pwm${ch} ]; then
        echo $ch > /sys/class/pwm/pwmchip0/export 2>/dev/null
    fi
    echo 20000000 > /sys/class/pwm/pwmchip0/pwm${ch}/period 2>/dev/null
    echo $CENTER > /sys/class/pwm/pwmchip0/pwm${ch}/duty_cycle 2>/dev/null
    echo 1 > /sys/class/pwm/pwmchip0/pwm${ch}/enable 2>/dev/null
done

# ── 工具函数 ──────────────────────────────
set_servo() {
    echo "$2" > "$1/duty_cycle"
}

move_to() {
    local pwm=$1 from=$2 to=$3 steps=$4 delay=$5
    for i in $(seq 1 $steps); do
        local pos=$(( from + (to - from) * i / steps ))
        set_servo $pwm $pos
        sleep $delay
    done
}

# ── 回中 ──────────────────────────────
set_servo $PWM_YAW $CENTER
set_servo $PWM_PITCH $CENTER
sleep 0.5

# ── 跳舞 ──────────────────────────────
YAW_LEFT=$((CENTER - STEP * 3))
YAW_RIGHT=$((CENTER + STEP * 3))
PITCH_DOWN=$((CENTER - STEP * 2))
PITCH_UP=$((CENTER + STEP * 2))

for round in 1 2 3; do
    # 向左 + 点头
    move_to $PWM_YAW $CENTER $YAW_LEFT 3 0.08
    move_to $PWM_PITCH $CENTER $PITCH_DOWN 2 0.1
    move_to $PWM_PITCH $PITCH_DOWN $CENTER 2 0.1

    # 向右 + 点头
    move_to $PWM_YAW $YAW_LEFT $YAW_RIGHT 6 0.08
    move_to $PWM_PITCH $CENTER $PITCH_DOWN 2 0.1
    move_to $PWM_PITCH $PITCH_DOWN $CENTER 2 0.1

    # 回中
    move_to $PWM_YAW $YAW_RIGHT $CENTER 3 0.08
    sleep 0.2
done

# ── 鞠躬 ──────────────────────────────
for bow in 1 2; do
    move_to $PWM_PITCH $CENTER $PITCH_UP 3 0.08
    move_to $PWM_PITCH $PITCH_UP $PITCH_DOWN 4 0.08
    move_to $PWM_PITCH $PITCH_DOWN $CENTER 3 0.08
    sleep 0.15
done

# ── 回中 ──────────────────────────────
set_servo $PWM_YAW $CENTER
set_servo $PWM_PITCH $CENTER
echo "舞蹈完成!"
```

---

## 8. Python 实现

如果你需要更精细的控制或集成到其他 Python 项目中：

```python
#!/usr/bin/env python3
"""
RDK X5 Servo Controller
PWM-based pan-tilt control via Linux sysfs
"""
import time
import os

class Servo:
    """单个舵机控制"""
    
    def __init__(self, chip=0, channel=0):
        self.pwm_path = f"/sys/class/pwm/pwmchip{chip}/pwm{channel}"
        self.chip_path = f"/sys/class/pwm/pwmchip{chip}"
        self.channel = channel
        self._init_pwm()
    
    def _init_pwm(self):
        # 导出通道
        if not os.path.exists(self.pwm_path):
            with open(f"{self.chip_path}/export", "w") as f:
                f.write(str(self.channel))
        # 设置周期 20ms
        self._write("period", "20000000")
        # 设置中位
        self._write("duty_cycle", "1500000")
        # 启用
        self._write("enable", "1")
    
    def _write(self, attr, value):
        with open(f"{self.pwm_path}/{attr}", "w") as f:
            f.write(value)
    
    def set_duty(self, duty_ns):
        """设置占空比（纳秒）"""
        duty_ns = max(500000, min(2500000, int(duty_ns)))
        self._write("duty_cycle", str(duty_ns))
    
    def set_angle(self, angle):
        """设置角度（0-180°）"""
        duty = 500000 + int(angle / 180 * 2000000)
        self.set_duty(duty)
    
    def move_to(self, target_duty, steps=5, delay=0.08):
        """平滑移动到目标位置"""
        # 读取当前 duty
        with open(f"{self.pwm_path}/duty_cycle", "r") as f:
            current = int(f.read().strip())
        
        for i in range(1, steps + 1):
            pos = current + (target_duty - current) * i // steps
            self.set_duty(pos)
            time.sleep(delay)


class PanTilt:
    """Pan-Tilt 云台控制"""
    
    CENTER = 1500000
    STEP = 100000
    
    def __init__(self, yaw_chip=0, yaw_ch=0, pitch_chip=0, pitch_ch=1):
        self.yaw = Servo(yaw_chip, yaw_ch)
        self.pitch = Servo(pitch_chip, pitch_ch)
    
    def center(self):
        """回到中位"""
        self.yaw.set_duty(self.CENTER)
        self.pitch.set_duty(self.CENTER)
    
    def nod(self):
        """点头"""
        down = self.CENTER - self.STEP * 2
        self.pitch.move_to(down, steps=2, delay=0.1)
        self.pitch.move_to(self.CENTER, steps=2, delay=0.1)
    
    def shake(self):
        """摇头"""
        left = self.CENTER - self.STEP * 3
        right = self.CENTER + self.STEP * 3
        self.yaw.move_to(left, steps=3, delay=0.08)
        self.yaw.move_to(right, steps=6, delay=0.08)
        self.yaw.move_to(self.CENTER, steps=3, delay=0.08)
    
    def bow(self):
        """鞠躬"""
        up = self.CENTER + self.STEP * 2
        down = self.CENTER - self.STEP * 2
        self.pitch.move_to(up, steps=3, delay=0.08)
        self.pitch.move_to(down, steps=4, delay=0.08)
        self.pitch.move_to(self.CENTER, steps=3, delay=0.08)
    
    def dance(self):
        """跳舞！"""
        self.center()
        time.sleep(0.5)
        
        for _ in range(3):
            # 左右摇 + 点头
            left = self.CENTER - self.STEP * 3
            self.yaw.move_to(left, steps=3, delay=0.08)
            self.nod()
            
            right = self.CENTER + self.STEP * 3
            self.yaw.move_to(right, steps=6, delay=0.08)
            self.nod()
            
            self.yaw.move_to(self.CENTER, steps=3, delay=0.08)
            time.sleep(0.2)
        
        # 鞠躬
        self.bow()
        time.sleep(0.15)
        self.bow()
        
        self.center()
        print("舞蹈完成!")


if __name__ == "__main__":
    pt = PanTilt()
    pt.dance()
```

---

## 9. 安全注意事项

### 电流冲击

**这是最重要的安全问题。** 舵机在快速转动时电流很大（峰值可达 700mA-1A 每个）。

防护措施：
1. **渐进移动**：永远不要一步跳转到目标角度，分 3-5 步过渡
2. **外部供电**：两个舵机建议用独立 5V 电源
3. **限速**：每步变化不超过 200000ns，步间延迟不低于 50ms
4. **避免堵转**：不要驱动舵机超过机械极限

### 角度限制

```
安全范围：duty_cycle 500000 ~ 2500000 (0° ~ 180°)
建议范围：duty_cycle 700000 ~ 2300000 (18° ~ 162°)  // 留余量
```

### 掉电保护

PWM 输出停止后，舵机不再保持力矩。如果需要长时间保持位置，要持续输出 PWM 信号。

---

## 10. 常见问题

### Q: 舵机不动

**A**: 检查：
1. PWM 是否导出：`ls /sys/class/pwm/pwmchip0/pwm0/`
2. PWM 是否启用：`cat /sys/class/pwm/pwmchip0/pwm0/enable` → 应该是 1
3. 信号线是否接对引脚
4. 供电是否充足

### Q: 板子突然重启

**A**: 舵机电流冲击导致。解决方案：
- 使用渐进移动，不要一步到位
- 使用外部 5V 电源给舵机供电
- 减小运动幅度和速度

### Q: 运动不够平滑

**A**: 增加步数、减小每步变化量。例如从 3 步增加到 10 步，delay 相应减小。

### Q: 两个舵机同时动的时候卡顿

**A**: Shell 脚本中两个舵机是串行控制的。如果需要同时运动，可以用 Python 的多线程，或者在一个循环里交替写两个舵机的 duty_cycle。

### Q: Shell 里用 bc 报错

**A**: RDK X5 默认没装 `bc`。用 `$(( ))` 做整数运算：

```bash
# 错误（需要 bc）
pos=$(echo "1500000 + 100000 * 3" | bc)

# 正确（纯 bash）
pos=$(( 1500000 + 100000 * 3 ))
```

---

*本教程基于 RDK X5 实际开发经验编写，所有代码经过实测验证。*
