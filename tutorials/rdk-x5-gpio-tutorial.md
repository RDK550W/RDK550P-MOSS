# RDK X5 GPIO 入门：按钮、LED 与中断控制

> 完整实战教程 | Hobot.GPIO 库 + 数字输入输出 + 中断事件
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

掌握 RDK X5 上 GPIO 的使用方法：
- 使用 `Hobot.GPIO` Python 库控制数字引脚
- 点亮 LED、读取按钮状态
- 使用中断回调实现事件驱动编程
- 结合其他外设（传感器、继电器等）

**与树莓派的对比：** RDK X5 的 GPIO 库 `Hobot.GPIO` 接口设计与树莓派的 `RPi.GPIO` 几乎一致。如果你有树莓派开发经验，上手会非常快。

---

## 目录

1. [硬件准备](#1-硬件准备)
2. [40pin 引脚定义](#2-40pin-引脚定义)
3. [Hobot.GPIO 基础](#3-hobotgpio-基础)
   - 3.1 引脚编号模式
   - 3.2 输出控制（点亮 LED）
   - 3.3 输入读取（按钮）
   - 3.4 中断与事件回调
4. [实战项目：按钮控制 LED](#4-实战项目按钮控制-led)
5. [进阶：呼吸灯效果](#5-进阶呼吸灯效果)
6. [进阶：多传感器输入](#6-进阶多传感器输入)
7. [完整参考代码](#7-完整参考代码)
8. [常见问题](#8-常见问题)

---

## 1. 硬件准备

| 硬件 | 数量 | 说明 |
|------|------|------|
| RDK X5 | 1 | 带 40pin GPIO 接口 |
| LED | 1-2 | 任意颜色，5mm 直插 |
| 220Ω 电阻 | 1-2 | LED 限流电阻 |
| 按钮/开关 | 1 | 常开型轻触按钮 |
| 10KΩ 电阻 | 1 | 按钮下拉电阻（可选） |
| 面包板 + 杜邦线 | 若干 | |

**基本接线（LED）：**
```
GPIO 引脚 → 220Ω 电阻 → LED 正极(长脚) → LED 负极(短脚) → GND
```

**基本接线（按钮）：**
```
3.3V → 按钮 → GPIO 引脚
                ↓
             10KΩ → GND  (下拉电阻)
```

---

## 2. 40pin 引脚定义

RDK X5 提供标准 40pin GPIO 接口，与树莓派物理布局兼容：

```
                    RDK X5 40pin
              ┌─────────────────────┐
              │ [1]  3.3V  │  5V [2]│
              │ [3]  SDA   │  5V [4]│
              │ [5]  SCL   │ GND [6]│
              │ [7]  GPIO  │ TXD [8]│
              │ [9]  GND   │ RXD[10]│
              │[11]  GPIO  │GPIO[12]│
              │[13]  GPIO  │ GND[14]│
              │[15]  GPIO  │GPIO[16]│
              │[17]  3.3V  │GPIO[18]│
              │[19]  MOSI  │ GND[20]│
              │[21]  MISO  │GPIO[22]│
              │[23]  SCLK  │ CE0[24]│
              │[25]  GND   │ CE1[26]│
              │[27]  SDA1  │SCL1[28]│
              │[29]  GPIO  │ GND[30]│
              │[31]  GPIO  │GPIO[32]│  ← PWM0
              │[33]  GPIO  │ GND[34]│  ← PWM1
              │[35]  GPIO  │GPIO[36]│
              │[37]  GPIO  │GPIO[38]│
              │[39]  GND   │GPIO[40]│
              └─────────────────────┘
```

> **注意**：不是所有引脚都支持 GPIO 功能，部分引脚有特殊功能（I2C、SPI、UART、PWM）。具体引脚功能请参考地瓜官方文档。

---

## 3. Hobot.GPIO 基础

### 3.1 引脚编号模式

```python
import Hobot.GPIO as GPIO

# BOARD 模式：使用物理引脚编号（推荐，直观）
GPIO.setmode(GPIO.BOARD)

# BCM 模式：使用 BCM GPIO 编号
# GPIO.setmode(GPIO.BCM)

# SOC 模式：使用 SoC 内部编号
# GPIO.setmode(GPIO.SOC)
```

**建议使用 BOARD 模式** — 编号就是引脚的物理位置，对着板子数就行，不容易搞错。

### 3.2 输出控制（点亮 LED）

```python
import Hobot.GPIO as GPIO
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

# 设置引脚为输出模式
led_pin = 31
GPIO.setup(led_pin, GPIO.OUT)

# 点亮 LED
GPIO.output(led_pin, GPIO.HIGH)
time.sleep(1)

# 熄灭 LED
GPIO.output(led_pin, GPIO.LOW)

# 清理（释放 GPIO 资源）
GPIO.cleanup()
```

**闪烁 LED：**

```python
GPIO.setup(led_pin, GPIO.OUT)
try:
    while True:
        GPIO.output(led_pin, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(led_pin, GPIO.LOW)
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
```

### 3.3 输入读取（按钮）

```python
button_pin = 37
GPIO.setup(button_pin, GPIO.IN)

# 读取当前状态
state = GPIO.input(button_pin)
print(f"按钮状态: {'按下' if state == GPIO.HIGH else '松开'}")
```

**轮询方式检测按钮：**

```python
prev = None
while True:
    curr = GPIO.input(button_pin)
    if curr != prev:
        print(f"按钮 {'按下' if curr else '松开'}")
        prev = curr
    time.sleep(0.05)  # 50ms 轮询间隔（也起到消抖作用）
```

### 3.4 中断与事件回调

轮询会占用 CPU。更优雅的方式是使用中断：

```python
def button_callback(channel):
    print(f"按钮事件! 引脚 {channel}")

# 注册中断回调
GPIO.setup(button_pin, GPIO.IN)
GPIO.add_event_detect(
    button_pin,
    GPIO.RISING,          # 上升沿触发（按下）
    callback=button_callback,
    bouncetime=200        # 消抖时间 200ms
)

# 主线程继续做其他事
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()
```

**事件类型：**
- `GPIO.RISING`：低→高（上升沿）
- `GPIO.FALLING`：高→低（下降沿）
- `GPIO.BOTH`：任意变化

**阻塞等待事件：**

```python
# 等待按钮按下，最多等 5 秒
channel = GPIO.wait_for_edge(button_pin, GPIO.RISING, timeout=5000)
if channel is None:
    print("超时，没有按下")
else:
    print("按钮已按下！")
```

---

## 4. 实战项目：按钮控制 LED

最经典的入门项目 — 按下按钮点亮 LED，松开熄灭：

```python
#!/usr/bin/env python3
"""按钮控制 LED"""
import Hobot.GPIO as GPIO
import time
import signal
import sys

def signal_handler(sig, frame):
    GPIO.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# 引脚定义
LED_PIN = 31      # BOARD 编号
BUTTON_PIN = 37   # BOARD 编号

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN)

# 初始状态：LED 灭
GPIO.output(LED_PIN, GPIO.LOW)

print("按住按钮点亮 LED，松开熄灭。Ctrl+C 退出")

prev_state = None
try:
    while True:
        state = GPIO.input(BUTTON_PIN)
        if state != prev_state:
            GPIO.output(LED_PIN, state)
            prev_state = state
            print(f"LED {'亮' if state else '灭'}")
        time.sleep(0.05)
finally:
    GPIO.cleanup()
```

---

## 5. 进阶：呼吸灯效果

利用软件 PWM 实现 LED 渐亮渐灭：

```python
#!/usr/bin/env python3
"""LED 呼吸灯效果（软件 PWM）"""
import Hobot.GPIO as GPIO
import time

LED_PIN = 31
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LED_PIN, GPIO.OUT)

# 使用 PWM 类
pwm = GPIO.PWM(LED_PIN, 1000)  # 1000Hz
pwm.start(0)  # 初始占空比 0%

try:
    while True:
        # 渐亮
        for dc in range(0, 101, 2):
            pwm.ChangeDutyCycle(dc)
            time.sleep(0.02)
        # 渐灭
        for dc in range(100, -1, -2):
            pwm.ChangeDutyCycle(dc)
            time.sleep(0.02)
except KeyboardInterrupt:
    pwm.stop()
    GPIO.cleanup()
```

> **注意**：这是软件 PWM，精度和频率不如硬件 PWM。对于 LED 呼吸灯效果足够了，但如果要精确控制舵机，请使用硬件 PWM（sysfs 接口，详见舵机教程）。

---

## 6. 进阶：多传感器输入

GPIO 可以读取各种数字传感器：

### 红外避障传感器

```python
IR_PIN = 22  # 红外传感器信号线

GPIO.setup(IR_PIN, GPIO.IN)

def obstacle_detected(channel):
    print("检测到障碍物！")

GPIO.add_event_detect(IR_PIN, GPIO.FALLING,
                      callback=obstacle_detected,
                      bouncetime=300)
```

### 人体红外（PIR）传感器

```python
PIR_PIN = 15

GPIO.setup(PIR_PIN, GPIO.IN)

def motion_detected(channel):
    print(f"检测到人体移动！时间: {time.strftime('%H:%M:%S')}")

GPIO.add_event_detect(PIR_PIN, GPIO.RISING,
                      callback=motion_detected,
                      bouncetime=2000)  # PIR 有较长的稳定时间
```

### 继电器控制

```python
RELAY_PIN = 29

GPIO.setup(RELAY_PIN, GPIO.OUT)

# 打开继电器（通电）
GPIO.output(RELAY_PIN, GPIO.HIGH)

# 关闭继电器（断电）
GPIO.output(RELAY_PIN, GPIO.LOW)
```

---

## 7. 完整参考代码

### GPIO 工具类

一个封装好的 GPIO 工具类，方便在项目中复用：

```python
#!/usr/bin/env python3
"""RDK X5 GPIO 工具类"""
import Hobot.GPIO as GPIO
import time
import atexit


class Pin:
    """GPIO 引脚封装"""
    
    _initialized = False
    
    @classmethod
    def _ensure_init(cls):
        if not cls._initialized:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BOARD)
            atexit.register(GPIO.cleanup)
            cls._initialized = True
    
    def __init__(self, pin_num, mode=GPIO.OUT, initial=GPIO.LOW):
        Pin._ensure_init()
        self.pin = pin_num
        self.mode = mode
        GPIO.setup(pin_num, mode)
        if mode == GPIO.OUT:
            GPIO.output(pin_num, initial)
    
    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)
    
    def off(self):
        GPIO.output(self.pin, GPIO.LOW)
    
    def toggle(self):
        current = GPIO.input(self.pin)
        GPIO.output(self.pin, not current)
    
    def read(self):
        return GPIO.input(self.pin)
    
    def on_change(self, callback, edge=GPIO.BOTH, bouncetime=200):
        GPIO.add_event_detect(self.pin, edge,
                              callback=callback,
                              bouncetime=bouncetime)


# 使用示例
if __name__ == "__main__":
    led = Pin(31, GPIO.OUT)
    button = Pin(37, GPIO.IN)
    
    def on_press(ch):
        led.toggle()
        print("Toggle!")
    
    button.on_change(on_press, edge=GPIO.RISING)
    
    print("等待按钮...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
```

---

## 8. 常见问题

### Q: GPIO.setup() 报错 permission denied

**A**: 需要 root 权限运行：
```bash
sudo python3 your_script.py
```

### Q: 按钮抖动导致多次触发

**A**: 使用 `bouncetime` 参数消抖：
```python
GPIO.add_event_detect(pin, GPIO.RISING, callback=func, bouncetime=200)
```
200ms 消抖时间适合大多数按钮。

### Q: Hobot.GPIO 和 RPi.GPIO 的区别

**A**: 接口几乎一致，主要区别：
- 包名不同：`import Hobot.GPIO` vs `import RPi.GPIO`
- 引脚编号不同：BOARD 模式的物理位置一样，但 BCM/SOC 编号不同
- 部分高级功能可能有差异

### Q: 如何知道某个引脚支持什么功能？

**A**: 查看地瓜官方 40pin 引脚定义文档，或使用：
```python
info = GPIO.pin_info(pin_number)
print(info)
```

### Q: GPIO 与 PWM 舵机控制的区别

**A**: 
- `Hobot.GPIO` 的 PWM 是**软件 PWM**，适合 LED 调光等对精度要求不高的场景
- 舵机控制需要**硬件 PWM**，使用 sysfs 接口（`/sys/class/pwm/`），精度更高
- 详见本系列的舵机控制教程

---

*本教程基于 RDK X5 实际开发经验编写，代码经过实测验证。*
