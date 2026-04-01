# RDK X5 BPU 目标检测实战：YOLOv5 从图片到实时检测

> 完整实战教程 | BPU 硬件加速 + YOLOv5 推理 + 后处理 + 可视化
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

在 RDK X5 上使用 BPU（Brain Processing Unit）硬件加速运行 YOLOv5 目标检测：
- 理解 RDK X5 的 BPU 加速推理架构
- 使用 `hobot_dnn` Python 接口加载和运行模型
- 掌握 NV12 图像预处理流程
- 实现 YOLOv5 后处理（NMS + 画框）
- 从单张图片检测到 MIPI 摄像头实时检测

**为什么用 BPU？**

RDK X5 内置 BPU 加速器，专为深度学习推理优化。相比纯 CPU 推理，BPU 可以提供 10-50 倍的加速，同时功耗更低。系统预装了 30+ 个已转换好的模型（`.bin` 格式），包括 YOLOv5、YOLOv8、FCOS、SSD 等。

---

## 目录

1. [BPU 推理架构概览](#1-bpu-推理架构概览)
2. [环境确认](#2-环境确认)
3. [模型与示例文件](#3-模型与示例文件)
4. [快速体验：图片分类](#4-快速体验图片分类)
5. [YOLOv5 目标检测详解](#5-yolov5-目标检测详解)
   - 5.1 加载模型
   - 5.2 图像预处理（BGR → NV12）
   - 5.3 BPU 推理
   - 5.4 后处理与 NMS
   - 5.5 结果可视化
6. [完整代码：单张图片检测](#6-完整代码单张图片检测)
7. [进阶：MIPI 摄像头实时检测](#7-进阶mipi-摄像头实时检测)
8. [性能优化技巧](#8-性能优化技巧)
9. [常见问题](#9-常见问题)

---

## 1. BPU 推理架构概览

```
                RDK X5 推理流程
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐
│  输入图像 │ →  │ 预处理    │ →  │ BPU 推理 │ →  │ 后处理    │
│ (BGR/NV12)│    │ resize   │    │ .bin模型 │    │ NMS+画框  │
│          │    │ BGR→NV12 │    │ 硬件加速  │    │ 输出结果  │
└─────────┘    └──────────┘    └─────────┘    └──────────┘
```

**关键概念：**
- **`.bin` 模型**：地瓜机器人的 BPU 专用格式，由原始模型（ONNX/Caffe 等）通过工具链转换而来
- **NV12 输入**：BPU 的模型通常期望 NV12 格式输入（与摄像头输出格式一致，零拷贝）
- **`hobot_dnn`**：Python 推理接口，封装了模型加载、推理、tensor 管理
- **`libpostprocess.so`**：系统预装的 C 后处理库，提供各种模型的 NMS 实现

---

## 2. 环境确认

```bash
# 确认 hobot_dnn 可用
python3 -c "from hobot_dnn import pyeasy_dnn; print('OK')"

# 如果上面报错，试试这个
python3 -c "from hobot_dnn_rdkx5 import pyeasy_dnn; print('OK')"

# 确认后处理库
ls /usr/lib/libpostprocess.so

# 确认预装模型
ls /opt/hobot/model/x5/basic/
```

你应该能看到大量 `.bin` 模型文件：

```
yolov5s_672x672_nv12.bin
yolov8_640x640_nv12.bin
mobilenetv1_224x224_nv12.bin
googlenet_224x224_nv12.bin
...
```

---

## 3. 模型与示例文件

系统预装了完整的示例代码和模型：

```
/app/pydev_demo/
├── 01_basic_sample/          # 图像分类（MobileNet、GoogleNet 等）
├── 02_usb_camera_sample/     # USB 摄像头 + 检测
├── 03_mipi_camera_sample/    # MIPI 摄像头
├── 04_segment_sample/        # 语义分割
├── 05_web_display_camera_sample/  # Web 实时显示
├── 06_yolov3_sample/         # YOLOv3 检测
├── 07_yolov5_sample/         # YOLOv5 检测
├── 09_yolov5x_sample/        # YOLOv5x 大模型
├── 10_ssd_mobilenetv1_sample/ # SSD 检测
├── 11_centernet_sample/      # CenterNet 检测
├── 12_yolov5s_v6_v7_sample/  # YOLOv5 v6/v7
└── models/                   # 软链接到 /opt/hobot/model/x5/basic/
```

---

## 4. 快速体验：图片分类

先跑一个最简单的分类模型，理解基本流程：

```python
#!/usr/bin/env python3
"""RDK X5 BPU 图像分类快速体验"""
import numpy as np
import cv2

try:
    from hobot_dnn import pyeasy_dnn as dnn
except ImportError:
    from hobot_dnn_rdkx5 import pyeasy_dnn as dnn


def bgr2nv12(image):
    """BGR 图像转 NV12 格式（BPU 模型所需的输入格式）"""
    height, width = image.shape[0], image.shape[1]
    area = height * width
    yuv420p = cv2.cvtColor(image, cv2.COLOR_BGR2YUV_I420).reshape((area * 3 // 2,))
    y = yuv420p[:area]
    uv_planar = yuv420p[area:].reshape((2, area // 4))
    uv_packed = uv_planar.transpose((1, 0)).reshape((area // 2,))
    nv12 = np.zeros_like(yuv420p)
    nv12[:area] = y
    nv12[area:] = uv_packed
    return nv12


# 1. 加载模型
models = dnn.load('/opt/hobot/model/x5/basic/mobilenetv1_224x224_nv12.bin')
model = models[0]

# 2. 查看模型信息
print(f"输入 shape: {model.inputs[0].properties.shape}")
print(f"输入 layout: {model.inputs[0].properties.layout}")
print(f"输出 shape: {model.outputs[0].properties.shape}")

# 3. 预处理
img = cv2.imread("test.jpg")
h, w = 224, 224  # 模型期望的输入尺寸
resized = cv2.resize(img, (w, h))
nv12 = bgr2nv12(resized)

# 4. 推理
outputs = model.forward(nv12)

# 5. 获取结果
# 分类模型输出是 1000 类的概率向量
probs = outputs[0].buffer.flatten()
top5_idx = np.argsort(probs)[-5:][::-1]

print("\nTop 5 预测结果：")
for idx in top5_idx:
    print(f"  类别 {idx}: 概率 {probs[idx]:.4f}")
```

---

## 5. YOLOv5 目标检测详解

### 5.1 加载模型

```python
try:
    from hobot_dnn import pyeasy_dnn as dnn
except ImportError:
    from hobot_dnn_rdkx5 import pyeasy_dnn as dnn

# 加载 YOLOv5s 模型
models = dnn.load('/opt/hobot/model/x5/basic/yolov5s_672x672_nv12.bin')
model = models[0]

# 查看输入输出信息
print(f"输入: {model.inputs[0].properties.shape}")   # [1, 672, 672, 3]
print(f"输出数量: {len(model.outputs)}")              # 3 个输出头

for i, out in enumerate(model.outputs):
    print(f"输出[{i}]: {out.properties.shape}")
```

`dnn.load()` 返回一个模型列表（一个 `.bin` 文件可能包含多个模型），通常取 `[0]`。

### 5.2 图像预处理（BGR → NV12）

BPU 模型的输入格式是 NV12，不是常见的 BGR/RGB。需要手动转换：

```python
def bgr2nv12(image):
    """将 BGR 图像转换为 NV12 格式"""
    height, width = image.shape[0], image.shape[1]
    area = height * width
    
    # BGR → YUV I420
    yuv420p = cv2.cvtColor(image, cv2.COLOR_BGR2YUV_I420).reshape((area * 3 // 2,))
    
    # 分离 Y 和 UV 平面
    y = yuv420p[:area]
    uv_planar = yuv420p[area:].reshape((2, area // 4))
    
    # UV planar → UV interleaved（I420 → NV12 的关键步骤）
    uv_packed = uv_planar.transpose((1, 0)).reshape((area // 2,))
    
    # 拼接
    nv12 = np.zeros_like(yuv420p)
    nv12[:area] = y
    nv12[area:] = uv_packed
    return nv12
```

**I420 vs NV12 的区别：**
- I420：Y 平面 + U 平面 + V 平面（三个独立平面）
- NV12：Y 平面 + UV 交织平面（UV 配对存储）

OpenCV 只能转到 I420，所以需要手动将 U、V 交织打包成 NV12。

**完整预处理流程：**

```python
# 读取原始图像
img = cv2.imread("test.jpg")

# resize 到模型尺寸
h, w = 672, 672  # YOLOv5s 的输入尺寸
resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)

# BGR → NV12
nv12_data = bgr2nv12(resized)
```

### 5.3 BPU 推理

```python
import time

t0 = time.time()
outputs = model.forward(nv12_data)
t1 = time.time()
print(f"推理耗时: {(t1-t0)*1000:.1f} ms")
```

`forward()` 将 NV12 数据送入 BPU 执行推理，返回输出 tensor 列表。

### 5.4 后处理与 NMS

YOLOv5 的后处理比较复杂，系统预装了 C 实现的后处理库 `libpostprocess.so`，通过 `ctypes` 调用：

```python
import ctypes
import json

# 加载后处理库
libpostprocess = ctypes.CDLL('/usr/lib/libpostprocess.so')

# 配置后处理参数
class Yolov5PostProcessInfo_t(ctypes.Structure):
    _fields_ = [
        ("height", ctypes.c_int),          # 模型输入高
        ("width", ctypes.c_int),           # 模型输入宽
        ("ori_height", ctypes.c_int),      # 原始图像高
        ("ori_width", ctypes.c_int),       # 原始图像宽
        ("score_threshold", ctypes.c_float), # 置信度阈值
        ("nms_threshold", ctypes.c_float),   # NMS IoU 阈值
        ("nms_top_k", ctypes.c_int),         # 最大检测数
        ("is_pad_resize", ctypes.c_int)      # 是否 padding resize
    ]

info = Yolov5PostProcessInfo_t()
info.height = 672
info.width = 672
info.ori_height = img.shape[0]  # 原始图像尺寸
info.ori_width = img.shape[1]
info.score_threshold = 0.4
info.nms_threshold = 0.45
info.nms_top_k = 20
info.is_pad_resize = 0
```

**调用后处理获取结果：**

```python
# 将推理输出转为 C 结构体（细节见完整代码）
# ... 设置 output_tensors ...

# 获取 JSON 格式的检测结果
get_result = libpostprocess.Yolov5PostProcess
get_result.argtypes = [ctypes.POINTER(Yolov5PostProcessInfo_t)]
get_result.restype = ctypes.c_char_p

result_str = get_result(ctypes.pointer(info))
result_str = result_str.decode('utf-8')

# 解析结果
data = json.loads(result_str[16:])  # 跳过前缀
for det in data:
    bbox = det['bbox']    # [x1, y1, x2, y2]
    score = det['score']  # 置信度
    name = det['name']    # 类别名称
    print(f"{name}: {score:.2f} at {bbox}")
```

### 5.5 结果可视化

```python
for det in data:
    bbox = det['bbox']
    score = det['score']
    name = det['name']
    
    # 画检测框
    cv2.rectangle(img,
        (int(bbox[0]), int(bbox[1])),
        (int(bbox[2]), int(bbox[3])),
        (0, 255, 0), 2)
    
    # 标注类别和置信度
    label = f'{name} {score:.2f}'
    cv2.putText(img, label,
        (int(bbox[0]), int(bbox[1]) - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

cv2.imwrite('result.jpg', img)
```

---

## 6. 完整代码：单张图片检测

```python
#!/usr/bin/env python3
"""
RDK X5 YOLOv5 目标检测
使用 BPU 硬件加速推理
"""
import numpy as np
import cv2
import ctypes
import json
import time

try:
    from hobot_dnn import pyeasy_dnn as dnn
except ImportError:
    from hobot_dnn_rdkx5 import pyeasy_dnn as dnn

# ── ctypes 结构体定义 ──────────────────────────

class hbSysMem_t(ctypes.Structure):
    _fields_ = [
        ("phyAddr", ctypes.c_double),
        ("virAddr", ctypes.c_void_p),
        ("memSize", ctypes.c_int)
    ]

class hbDNNQuantiScale_t(ctypes.Structure):
    _fields_ = [
        ("scaleLen", ctypes.c_int),
        ("scaleData", ctypes.POINTER(ctypes.c_float)),
        ("zeroPointLen", ctypes.c_int),
        ("zeroPointData", ctypes.c_char_p)
    ]

class hbDNNQuantiShift_t(ctypes.Structure):
    _fields_ = [
        ("shiftLen", ctypes.c_int),
        ("shiftData", ctypes.c_char_p)
    ]

class hbDNNTensorShape_t(ctypes.Structure):
    _fields_ = [
        ("dimensionSize", ctypes.c_int * 8),
        ("numDimensions", ctypes.c_int)
    ]

class hbDNNTensorProperties_t(ctypes.Structure):
    _fields_ = [
        ("validShape", hbDNNTensorShape_t),
        ("alignedShape", hbDNNTensorShape_t),
        ("tensorLayout", ctypes.c_int),
        ("tensorType", ctypes.c_int),
        ("shift", hbDNNQuantiShift_t),
        ("scale", hbDNNQuantiScale_t),
        ("quantiType", ctypes.c_int),
        ("quantizeAxis", ctypes.c_int),
        ("alignedByteSize", ctypes.c_int),
        ("stride", ctypes.c_int * 8)
    ]

class hbDNNTensor_t(ctypes.Structure):
    _fields_ = [
        ("sysMem", hbSysMem_t * 4),
        ("properties", hbDNNTensorProperties_t)
    ]

class Yolov5PostProcessInfo_t(ctypes.Structure):
    _fields_ = [
        ("height", ctypes.c_int),
        ("width", ctypes.c_int),
        ("ori_height", ctypes.c_int),
        ("ori_width", ctypes.c_int),
        ("score_threshold", ctypes.c_float),
        ("nms_threshold", ctypes.c_float),
        ("nms_top_k", ctypes.c_int),
        ("is_pad_resize", ctypes.c_int)
    ]


# ── 工具函数 ──────────────────────────

def bgr2nv12(image):
    height, width = image.shape[0], image.shape[1]
    area = height * width
    yuv420p = cv2.cvtColor(image, cv2.COLOR_BGR2YUV_I420).reshape((area * 3 // 2,))
    y = yuv420p[:area]
    uv_planar = yuv420p[area:].reshape((2, area // 4))
    uv_packed = uv_planar.transpose((1, 0)).reshape((area // 2,))
    nv12 = np.zeros_like(yuv420p)
    nv12[:area] = y
    nv12[area:] = uv_packed
    return nv12


def get_hw(properties):
    if properties.layout == "NCHW":
        return properties.shape[2], properties.shape[3]
    return properties.shape[1], properties.shape[2]


def get_layout_int(layout_str):
    return 2 if layout_str == "NCHW" else 0


# ── 主程序 ──────────────────────────

def detect(image_path, model_path, score_thresh=0.4, nms_thresh=0.45):
    # 加载模型
    models = dnn.load(model_path)
    model = models[0]
    
    h, w = get_hw(model.inputs[0].properties)
    print(f"模型输入尺寸: {w}x{h}")
    
    # 读取和预处理图像
    img = cv2.imread(image_path)
    if img is None:
        print(f"无法读取图像: {image_path}")
        return
    
    org_h, org_w = img.shape[:2]
    resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    nv12_data = bgr2nv12(resized)
    
    # BPU 推理
    t0 = time.time()
    outputs = model.forward(nv12_data)
    t1 = time.time()
    print(f"BPU 推理耗时: {(t1-t0)*1000:.1f} ms")
    
    # 后处理
    libpostprocess = ctypes.CDLL('/usr/lib/libpostprocess.so')
    
    info = Yolov5PostProcessInfo_t()
    info.height = h
    info.width = w
    info.ori_height = org_h
    info.ori_width = org_w
    info.score_threshold = score_thresh
    info.nms_threshold = nms_thresh
    info.nms_top_k = 20
    info.is_pad_resize = 0
    
    output_tensors = (hbDNNTensor_t * len(outputs))()
    for i in range(len(outputs)):
        output_tensors[i].properties.tensorLayout = get_layout_int(
            outputs[i].properties.layout
        )
        
        if len(outputs[i].properties.scale_data) == 0:
            output_tensors[i].properties.quantiType = 0
            output_tensors[i].sysMem[0].virAddr = ctypes.cast(
                outputs[i].buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                ctypes.c_void_p
            )
        else:
            output_tensors[i].properties.quantiType = 2
            output_tensors[i].properties.scale.scaleData = (
                outputs[i].properties.scale_data.ctypes.data_as(
                    ctypes.POINTER(ctypes.c_float)
                )
            )
            output_tensors[i].sysMem[0].virAddr = ctypes.cast(
                outputs[i].buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                ctypes.c_void_p
            )
        
        for j in range(len(outputs[i].properties.shape)):
            output_tensors[i].properties.validShape.dimensionSize[j] = (
                outputs[i].properties.shape[j]
            )
        
        libpostprocess.Yolov5doProcess(output_tensors[i], ctypes.pointer(info), i)
    
    get_result = libpostprocess.Yolov5PostProcess
    get_result.argtypes = [ctypes.POINTER(Yolov5PostProcessInfo_t)]
    get_result.restype = ctypes.c_char_p
    
    result_str = get_result(ctypes.pointer(info))
    result_str = result_str.decode('utf-8')
    
    t2 = time.time()
    print(f"后处理耗时: {(t2-t1)*1000:.1f} ms")
    
    # 解析并可视化
    data = json.loads(result_str[16:])
    print(f"\n检测到 {len(data)} 个目标：")
    
    for det in data:
        bbox = det['bbox']
        score = det['score']
        name = det['name']
        print(f"  {name}: {score:.2f} at [{bbox[0]:.0f}, {bbox[1]:.0f}, {bbox[2]:.0f}, {bbox[3]:.0f}]")
        
        cv2.rectangle(img,
            (int(bbox[0]), int(bbox[1])),
            (int(bbox[2]), int(bbox[3])),
            (0, 255, 0), 2)
        cv2.putText(img, f'{name} {score:.2f}',
            (int(bbox[0]), int(bbox[1]) - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    output_path = image_path.rsplit('.', 1)[0] + '_result.jpg'
    cv2.imwrite(output_path, img)
    print(f"\n结果保存到: {output_path}")


if __name__ == '__main__':
    import sys
    image = sys.argv[1] if len(sys.argv) > 1 else '/app/pydev_demo/07_yolov5_sample/kite.jpg'
    model = '/opt/hobot/model/x5/basic/yolov5s_672x672_nv12.bin'
    detect(image, model)
```

---

## 7. 进阶：MIPI 摄像头实时检测

将摄像头采集与 BPU 推理结合，实现实时目标检测：

```python
#!/usr/bin/env python3
"""MIPI 摄像头 + BPU 实时目标检测"""
import numpy as np
import cv2
import time

try:
    from hobot_dnn import pyeasy_dnn as dnn
except ImportError:
    from hobot_dnn_rdkx5 import pyeasy_dnn as dnn

try:
    from hobot_vio import libsrcampy as srcampy
except ImportError:
    from hobot_vio_rdkx5 import libsrcampy as srcampy


# 加载模型（使用 640x640 的 YOLOv8 更新更快）
models = dnn.load('/opt/hobot/model/x5/basic/yolov8_640x640_nv12.bin')
model = models[0]

# 打开摄像头（输出 640x640 分辨率匹配模型）
cam = srcampy.Camera()
cam.open_cam(0, -1, -1, [640], [640], 640, 640)

print("实时检测中... Ctrl+C 退出")
frame_count = 0
start = time.time()

try:
    while True:
        # 采集 NV12 图像（已经是 640x640，无需 resize！）
        nv12 = cam.get_img(2, 640, 640)
        if nv12 is None:
            continue
        
        # 直接送入 BPU（零预处理！）
        outputs = model.forward(nv12)
        
        frame_count += 1
        if frame_count % 30 == 0:
            fps = frame_count / (time.time() - start)
            print(f"FPS: {fps:.1f}")
        
        # 后处理...（同上）
        
finally:
    cam.close_cam()
```

> **零拷贝优化**：当摄像头输出分辨率与模型输入尺寸一致时，NV12 数据可以直接送入 BPU，跳过 resize 和格式转换，大幅提升帧率。

---

## 8. 性能优化技巧

### 8.1 匹配摄像头分辨率和模型输入

```python
# 让摄像头直接输出模型期望的尺寸
# 模型是 640x640 → 摄像头也设置 640x640
cam.open_cam(0, -1, -1, [640], [640], 640, 640)
```

### 8.2 选择合适的模型

系统预装模型的速度和精度对比（参考值）：

| 模型 | 输入尺寸 | BPU 推理时间 | 适用场景 |
|------|---------|-------------|---------|
| YOLOv5s | 672x672 | ~15ms | 精度优先 |
| YOLOv8 | 640x640 | ~12ms | 均衡 |
| SSD MobileNetV1 | 300x300 | ~5ms | 速度优先 |
| FCOS | 512x512 | ~10ms | 均衡 |

### 8.3 降低后处理开销

- 提高 `score_threshold`（如 0.5→0.6）减少候选框
- 降低 `nms_top_k`（如 20→10）减少 NMS 计算量
- 使用 C 后处理库而不是纯 Python 实现

---

## 9. 常见问题

### Q: `dnn.load()` 报错

**A**: 确认模型文件路径正确，且是 `.bin` 格式。`.onnx` 或 `.pt` 不能直接加载，需要通过地瓜工具链转换。

### Q: 推理结果全是空的

**A**: 检查预处理是否正确。最常见的问题是 BGR→NV12 转换错误或 resize 尺寸不匹配模型输入。

### Q: 检测框位置偏移

**A**: 确认 `ori_height` 和 `ori_width` 设置为原始图像尺寸，`is_pad_resize` 与你的 resize 方式一致（0=直接 resize，1=保持比例 padding）。

### Q: 如何使用自己的模型？

**A**: 需要使用地瓜机器人的 OE（Open Explorer）工具链将 ONNX/Caffe 模型转换为 `.bin` 格式。具体步骤参考地瓜官方文档的"模型转换"章节。

### Q: `libpostprocess.so` 找不到

**A**: 这个库来自 `hobot-spdev` 包。确认已安装：
```bash
dpkg -l | grep hobot-spdev
```

---

*本教程基于 RDK X5 实际开发经验编写，使用系统预装的模型和示例验证。*
