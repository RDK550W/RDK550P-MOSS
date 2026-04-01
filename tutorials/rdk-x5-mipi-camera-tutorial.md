# RDK X5 MIPI 摄像头实战：从拍照到图像处理

> 完整实战教程 | MIPI 摄像头驱动 + NV12 图像处理 + OpenCV 集成
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

掌握 RDK X5 上 MIPI 摄像头的完整使用方法：
- 理解 RDK X5 摄像头与普通 USB 摄像头（V4L2）的区别
- 使用 `hobot_vio` 的 `libsrcampy` 接口采集图像
- NV12 色彩空间转换为 BGR/RGB
- 结合 OpenCV 进行图像处理和保存
- 构建一个可复用的拍照脚本

**为什么需要这篇教程？**

RDK X5 的 MIPI 摄像头**不走 V4L2 通道**，你用 `cv2.VideoCapture(0)` 是打不开的。必须通过地瓜机器人的 VIN/ISP 专用 API 来访问。这个坑很多初学者都会踩到。

---

## 目录

1. [硬件连接](#1-硬件连接)
2. [摄像头驱动架构](#2-摄像头驱动架构)
3. [安装依赖](#3-安装依赖)
4. [快速拍照](#4-快速拍照)
5. [代码详解](#5-代码详解)
   - 5.1 Camera 对象初始化
   - 5.2 NV12 格式解析
   - 5.3 NV12 → BGR 转换
   - 5.4 图像保存与处理
6. [完整拍照脚本](#6-完整拍照脚本)
7. [进阶应用](#7-进阶应用)
   - 7.1 连续采集（视频流）
   - 7.2 结合 AI 推理
   - 7.3 定时拍照监控
8. [常见问题](#8-常见问题)

---

## 1. 硬件连接

RDK X5 支持 MIPI CSI 接口的摄像头模组。

| 接口 | 说明 |
|------|------|
| MIPI CSI | 板载 FPC 连接器，支持 2-lane / 4-lane |
| 支持传感器 | IMX219、OV5647、IMX477 等常见 MIPI 传感器 |

**连接步骤：**
1. 断电状态下，将摄像头排线插入 MIPI CSI 接口
2. 注意排线方向（金属触点朝向板子）
3. 上电后系统会自动检测摄像头

确认摄像头是否被识别：

```bash
ls /dev/vin*
# 应该看到 /dev/vin0_cap 等设备
```

---

## 2. 摄像头驱动架构

RDK X5 的摄像头系统与常见的 Linux V4L2 框架不同：

```
普通 Linux:   摄像头 → V4L2 驱动 → /dev/video0 → OpenCV
RDK X5:       MIPI 摄像头 → VIN/ISP 硬件 → libsrcampy → 用户程序
```

地瓜机器人的 VIN（Video Input）模块直接对接 MIPI 传感器，经过 ISP（Image Signal Processor）处理后，输出 NV12 格式的图像数据。

**关键点：**
- 不能用 `cv2.VideoCapture()` 或 `v4l2` 工具
- 必须使用 `hobot_vio` 提供的 `libsrcampy` Python 接口
- 输出格式为 NV12（YUV420SP），不是 BGR/RGB

---

## 3. 安装依赖

`hobot_vio` 通常在 RDK X5 的系统镜像中已经预装。

```bash
# 确认 hobot_vio 是否可用
python3 -c "from hobot_vio import libsrcampy; print('OK')"
```

如果提示找不到，尝试：

```bash
python3 -c "from hobot_vio_rdkx5 import libsrcampy; print('OK')"
```

> **注意**：不同系统版本的包名可能不同（`hobot_vio` 或 `hobot_vio_rdkx5`）。建议写一个兼容导入：

```python
try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy
```

还需要 OpenCV 和 NumPy：

```bash
pip3 install opencv-python-headless numpy
```

---

## 4. 快速拍照

先来一个最简单的拍照脚本，确认摄像头能工作：

```python
#!/usr/bin/env python3
import numpy as np
import cv2

try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy

# 打开摄像头
cam = srcampy.Camera()
cam.open_cam(0, -1, -1, [1920], [1080], 1080, 1920)

# 采集一帧 NV12 数据
nv12 = cam.get_img(2, 1920, 1080)
cam.close_cam()

if nv12 is None:
    print("拍照失败！")
    exit(1)

# NV12 → BGR
nv12_array = np.frombuffer(nv12, dtype=np.uint8).reshape(1620, 1920)
bgr = cv2.cvtColor(nv12_array, cv2.COLOR_YUV2BGR_NV12)

# 保存
cv2.imwrite("photo.jpg", bgr)
print("拍照成功：photo.jpg")
```

运行：

```bash
python3 quick_snap.py
```

---

## 5. 代码详解

### 5.1 Camera 对象初始化

```python
cam = srcampy.Camera()
cam.open_cam(
    0,          # 摄像头 ID（通常为 0）
    -1,         # 传感器类型（-1 = 自动检测）
    -1,         # 帧率（-1 = 默认）
    [1920],     # 输出宽度列表
    [1080],     # 输出高度列表
    1080,       # ISP 输出高度
    1920        # ISP 输出宽度
)
```

**参数说明：**
- 第一个参数是摄像头编号，单摄像头一般为 0
- 宽高参数以列表形式传入，支持多路输出（不同分辨率）
- ISP 输出尺寸决定了硬件处理的分辨率

### 5.2 NV12 格式解析

`get_img()` 返回的是 NV12 格式的原始字节数据。

**什么是 NV12？**

NV12 是一种 YUV420 Semi-Planar 格式：
- Y 平面：亮度信息，每个像素一个 Y 值
- UV 平面：色度信息，每 2x2 个像素共享一组 UV 值

对于 1920x1080 的图像：
- Y 平面大小：1920 × 1080 = 2,073,600 字节
- UV 平面大小：1920 × 540 = 1,036,800 字节
- 总大小：3,110,400 字节

```python
# NV12 数据的 reshape 维度
# 高度 = 原始高度 × 1.5（因为 UV 平面是 Y 平面的一半）
# 1080 × 1.5 = 1620
nv12_array = np.frombuffer(nv12, dtype=np.uint8).reshape(1620, 1920)
```

> **重要**：reshape 的高度是 `原始高度 × 1.5`，不是 `原始高度`。这是 NV12 格式的特点 — Y 平面和 UV 平面是连续存储的。

### 5.3 NV12 → BGR 转换

OpenCV 提供了直接的色彩空间转换：

```python
bgr = cv2.cvtColor(nv12_array, cv2.COLOR_YUV2BGR_NV12)
```

转换后的 `bgr` 是标准的 OpenCV BGR 格式图像（shape: 1080 × 1920 × 3），可以直接用于后续处理。

如果需要 RGB 格式（例如给深度学习模型）：

```python
rgb = cv2.cvtColor(nv12_array, cv2.COLOR_YUV2RGB_NV12)
```

### 5.4 图像保存与处理

```python
# 保存为 JPEG
cv2.imwrite("output.jpg", bgr)

# 保存为 PNG（无损）
cv2.imwrite("output.png", bgr)

# 调整大小
resized = cv2.resize(bgr, (640, 360))

# 转为灰度图
gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

# 画框（例如目标检测后）
cv2.rectangle(bgr, (100, 100), (300, 300), (0, 255, 0), 2)
cv2.imwrite("annotated.jpg", bgr)
```

---

## 6. 完整拍照脚本

一个带错误处理和参数支持的完整版本：

```python
#!/usr/bin/env python3
"""
RDK X5 MIPI Camera Snapshot
Usage: python3 snap.py [output_path]
Default output: ./snapshot.jpg
"""
import sys
import os
import numpy as np
import cv2

try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy

# 配置
WIDTH = 1920
HEIGHT = 1080
NV12_HEIGHT = int(HEIGHT * 1.5)  # 1620

def capture(output_path="snapshot.jpg"):
    """采集一帧并保存为 JPEG"""
    cam = srcampy.Camera()
    
    try:
        # 打开摄像头
        cam.open_cam(0, -1, -1, [WIDTH], [HEIGHT], HEIGHT, WIDTH)
        
        # 采集 NV12 数据
        nv12 = cam.get_img(2, WIDTH, HEIGHT)
        if nv12 is None:
            print("ERROR: 图像采集失败")
            return False
        
        # NV12 → BGR
        nv12_array = np.frombuffer(nv12, dtype=np.uint8).reshape(NV12_HEIGHT, WIDTH)
        bgr = cv2.cvtColor(nv12_array, cv2.COLOR_YUV2BGR_NV12)
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 保存
        cv2.imwrite(output_path, bgr)
        print(f"OK: {output_path}")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False
        
    finally:
        cam.close_cam()


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "snapshot.jpg"
    success = capture(output)
    sys.exit(0 if success else 1)
```

---

## 7. 进阶应用

### 7.1 连续采集（视频流）

```python
import time

cam = srcampy.Camera()
cam.open_cam(0, -1, -1, [1920], [1080], 1080, 1920)

try:
    frame_count = 0
    start_time = time.time()
    
    while True:
        nv12 = cam.get_img(2, 1920, 1080)
        if nv12 is None:
            continue
        
        frame_count += 1
        
        # 每秒打印帧率
        elapsed = time.time() - start_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            print(f"FPS: {fps:.1f}")
            frame_count = 0
            start_time = time.time()
        
        # 在这里处理每一帧...
        nv12_array = np.frombuffer(nv12, dtype=np.uint8).reshape(1620, 1920)
        bgr = cv2.cvtColor(nv12_array, cv2.COLOR_YUV2BGR_NV12)
        
        # 例如：检测、推理、标注...
        
finally:
    cam.close_cam()
```

### 7.2 结合 AI 推理

RDK X5 内置 BPU（Brain Processing Unit）加速器，可以高效运行 AI 模型。结合摄像头可以实现：

- 目标检测（YOLO 系列）
- 人脸识别
- 姿态估计
- 场景分类

```python
# 伪代码示例
nv12 = cam.get_img(2, 1920, 1080)
bgr = nv12_to_bgr(nv12)

# 前处理
input_tensor = preprocess(bgr, target_size=(640, 640))

# BPU 推理
results = bpu_model.forward(input_tensor)

# 后处理 + 画框
for det in results:
    cv2.rectangle(bgr, det.bbox, (0, 255, 0), 2)
```

### 7.3 定时拍照监控

结合 cron 或简单的 while 循环实现定时拍照：

```bash
# 每 5 分钟拍一张照片
*/5 * * * * python3 /path/to/snap.py /path/to/photos/$(date +\%Y\%m\%d_\%H\%M\%S).jpg
```

---

## 8. 常见问题

### Q: `cv2.VideoCapture(0)` 打不开摄像头

**A**: RDK X5 的 MIPI 摄像头不走 V4L2，必须用 `libsrcampy`。这是最常见的误区。

### Q: `get_img()` 返回 None

**A**: 可能原因：
- 摄像头排线没插好
- `open_cam` 的分辨率参数不被传感器支持
- 另一个进程正在占用摄像头

检查摄像头设备：`ls /dev/vin*`

### Q: 图像颜色异常（偏色、偏绿）

**A**: 确认 `cvtColor` 使用的是 `COLOR_YUV2BGR_NV12` 而不是其他格式码。NV12 和 NV21 的 UV 排列不同，用错了会严重偏色。

### Q: reshape 报错

**A**: 确认 reshape 的高度是 `原始高度 × 1.5`。例如 1080p 图像：
- 正确：`reshape(1620, 1920)` — 1080 × 1.5 = 1620
- 错误：`reshape(1080, 1920)` — 数据量不够

### Q: 如何降低分辨率？

**A**: 在 `open_cam` 参数中指定更小的分辨率：

```python
cam.open_cam(0, -1, -1, [640], [480], 480, 640)
nv12 = cam.get_img(2, 640, 480)
nv12_array = np.frombuffer(nv12, dtype=np.uint8).reshape(720, 640)  # 480*1.5=720
```

---

*本教程基于 RDK X5 实际开发经验编写，代码经过实测验证。*
