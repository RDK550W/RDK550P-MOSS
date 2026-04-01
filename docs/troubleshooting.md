# 踩坑指南 (Troubleshooting)

这些都是实际调试中踩过的坑，能帮你省很多时间。

---

## 音频相关

### USB 麦克风必须开启 AGC

**症状：** 语音助手启动正常，但 VAD 永远检测不到语音。

**原因：** USB 麦克风的 Auto Gain Control (AGC) 关闭时，采集信号极弱（max ~0.03~0.09），Silero VAD 无法触发。

**解决：**
```bash
# 检查当前设置
amixer -c 0 contents

# 开启 AGC + 增益拉满
amixer -c 0 set 'Auto Gain Control' on
amixer -c 0 set 'Mic' 147
```

**注意：** amixer 设置重启后可能丢失！用 `alsactl store` 持久化，或在 systemd service 里加 ExecStartPre。

### USB 声卡不能同时录音和播放

**症状：** TTS 播放期间或播放后，录音数据变成全零/固定值。

**原因：** plughw:0,0 不支持全双工。arecord 和 aplay 同时打开同一个设备，capture 数据会被污染。

**解决：** 播放前 kill arecord 进程，播放完后再重启。代码里用 `is_speaking` 标志控制：
```python
# 播放前
is_speaking = True
# kill arecord subprocess

# 播放后
is_speaking = False
# reader 线程检测到 is_speaking=False 后重启 arecord
```

**隐蔽性：** 这个 bug 不会报错！arecord 正常启动、正常读数据，但数据全是无效固定值。只能通过观察数据异常发现。

### sherpa_onnx.Alsa 不可靠

**症状：** 间歇性返回固定值/陈旧数据，特别是 TTS 播放后。

**解决：** 弃用 `sherpa_onnx.Alsa`，改用 `subprocess.Popen` 跑 arecord：
```bash
arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -t raw
```
用 reader 线程持续读取 stdout。

### 排查音频问题的正确顺序

1. 先查 ALSA mixer 设置（`amixer -c 0 contents`）
2. 再测直接采集（用 arecord 录一段，看波形）
3. 最后才看代码逻辑

不要一上来就改代码阈值或回退版本。

---

## 舵机相关

### 必须用 Python 控制，不能用 Shell

**症状：** Shell 脚本控制舵机时动作卡顿、不流畅。

**原因：** Shell 每步 fork bc/sleep 进程的开销导致延迟不可控。

**解决：** 所有舵机控制都用 Python + 余弦缓动：
```python
import math, time

def move_eased(pwm_path, start, end, steps=20, duration=0.2):
    for i in range(steps + 1):
        t = i / steps
        ease = (1 - math.cos(t * math.pi)) / 2
        duty = int(start + (end - start) * ease)
        with open(f"{pwm_path}/duty_cycle", "w") as f:
            f.write(str(duty))
        time.sleep(duration / steps)
```

**铁律：**
- 每个动作至少 12~25 步插值
- 必须余弦缓动（cosine ease-in-out）
- 禁止单步跳变超过 300000ns
- 参考实现：`scripts/dance.py`

---

## 模型相关

### sherpa-onnx API 兼容性

- `OfflineRecognizer` 要用工厂方法 `from_sense_voice()`，不能直接传 config
- `OfflineSpeakerDiarizationResult` 在 1.12.30 不能直接迭代，需调 `result.sort_by_start_time()` 返回 list
- 每个 segment 有 `.speaker` / `.start` / `.end` / `.text` 属性

### 模型下载慢

GitHub 在国内下载很慢（~700KB/s），优先用 HuggingFace 镜像：
- `https://hf-mirror.com/` — 国内镜像

### pip 安装慢

用清华镜像：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple 包名
```

---

## 摄像头相关

### MIPI 摄像头不是 V4L2

RDK X5 的 MIPI 摄像头通过 VIN/ISP API 访问，不是标准 V4L2。

使用 hobot_vio 的 `libsrcampy.Camera` 拍照：
```python
from hobot_vio import libsrcampy
cam = libsrcampy.Camera()
cam.open_cam(0, 1, 30, 1920, 1080)
# 输出 NV12 格式，需要 OpenCV 转 BGR
```

设备节点：`/dev/vin0_cap` ~ `/dev/vin3_cap`

---

## OpenClaw 相关

### 上下文窗口不要设太大

如果用第三方 API 代理，contextWindow 不要盲目设最大值。代理可能处理不了大上下文，会导致诡异的认证错误（如 `invalid_grant`）。

建议：contextWindow 不超过 200000，关闭 context1m。

### 自动压缩

压缩在 `contextTokens > contextWindow - reserveTokens` 时触发。如果 contextWindow 设太大，压缩永远不会触发，上下文无限膨胀直到出错。

---

## 系统相关

### pyaudio 装不了

RDK X5 系统没有 `portaudio19-dev`，pyaudio 编译会失败。

替代方案：用 `subprocess.Popen` 跑 `arecord`，从 stdout 读取 PCM 数据。

### 后台任务超时

长时间运行的命令要注意 timeout 设置，否则会被 SIGTERM 杀掉。
