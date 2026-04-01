# 3D 模型文件

RDK550W 外壳和云台支架的 3D 模型，使用 **SolidWorks 2024** 设计。

## 文件结构

```
3d-model/
├── RDK550W装配体.SLDASM      # 主装配体（打开这个看整体）
├── 标准件/                    # 标准件（舵机、舵盘等，仅参考）
│   ├── Servo_PTK7465.SLDPRT  # PTK7465 舵机模型
│   └── 舵盘.SLDPRT
└── 零件库/                    # 需要 3D 打印的零件
    ├── P00_安装卡扣.SLDPRT
    ├── P01_顶座.SLDPRT        # 摄像头顶座
    ├── P02_顶座上盖.SLDPRT
    ├── P03_机械臂1.SLDPRT     # 云台连接臂
    ├── P04_机械臂2.SLDPRT
    ├── P05_机械臂3.SLDPRT
    ├── P06_主体后壳_X5版.SLDPRT  # 主体后壳（RDK X5 适配版）
    ├── P06_主体后壳.SLDPRT       # 主体后壳（通用版）
    ├── P07_主体外挂.SLDPRT
    ├── P08_主体正盖.SLDPRT
    ├── P09_主体正盖侧灯.SLDPRT
    ├── P10_主体正盖面板01.SLDPRT
    ├── P11_主体正盖面板02.SLDPRT
    ├── P12_主体正盖外挂.SLDPRT
    ├── 支座A.SLDPRT
    ├── 支座B.SLDPRT
    └── 支座C.SLDPRT
```

## 打印建议

- 材料：PLA 或 PETG 均可
- 层高：0.2mm
- 填充：20~30%
- RDK X5 用户请使用 `P06_主体后壳_X5版.SLDPRT`

## 没有 SolidWorks？

如果没有 SolidWorks 2024，可以：
1. 用免费的 [eDrawings Viewer](https://www.edrawingsviewer.com/) 查看
2. 在线查看：上传到 [3DViewer.net](https://3dviewer.net/)
3. 如果需要 STL 格式，可以用 FreeCAD 转换，或提 Issue 我来导出
