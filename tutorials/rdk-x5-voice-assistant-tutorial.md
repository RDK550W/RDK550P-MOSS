# 从零开始：在 RDK X5 上搭建离线语音助手

> 完整实战教程 | 唤醒词检测 + 语音识别 + AI 对话 + 语音合成
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

一个完整的离线语音助手系统：
- 说出唤醒词"五五零"，机器人回应"在呢"
- 然后说出你的指令，机器人识别后通过 AI 生成回答
- 最后用语音把回答读给你听

整个语音识别过程**完全离线运行**，不依赖任何云端 API。AI 对话部分可以对接任意大模型后端。

**技术栈：**
- **VAD（语音活动检测）**：Silero VAD — 轻量级，适合边缘设备
- **ASR（语音识别）**：SenseVoice — 阿里达摩院开源，支持中英日韩粤
- **推理框架**：sherpa-onnx — 新一代纯 C++ 推理引擎，原生支持 ARM
- **TTS（语音合成）**：edge-tts — 微软 Edge 浏览器 TTS 接口
- **音频采集/播放**：ALSA — Linux 原生音频驱动

---

## 目录

1. [硬件准备](#1-硬件准备)
2. [系统环境配置](#2-系统环境配置)
3. [安装依赖](#3-安装依赖)
4. [下载模型文件](#4-下载模型文件)
5. [音频设备测试](#5-音频设备测试)
6. [核心代码详解](#6-核心代码详解)
   - 6.1 VAD 语音活动检测
   - 6.2 ASR 语音识别
   - 6.3 唤醒词匹配
   - 6.4 音频采集架构
   - 6.5 TTS 语音合成
   - 6.6 完整交互流程
7. [完整代码](#7-完整代码)
8. [运行与测试](#8-运行与测试)
9. [常见问题与踩坑记录](#9-常见问题与踩坑记录)
10. [进阶优化方向](#10-进阶优化方向)

---

## 1. 硬件准备

| 硬件 | 说明 |
|------|------|
| RDK X5 开发板 | 地瓜机器人出品，ARM aarch64，8GB 内存 |
| USB 声卡模块 | 推荐带麦克风+扬声器的一体模块（如 Jieli UACDemoV1.0） |
| 麦克风 | USB 声卡自带或外接 |
| 扬声器 | USB 声卡自带或 3.5mm 外接 |

> **为什么用 USB 声卡？** RDK X5 板载的 ES8326 音频芯片虽然支持双工，但实测在同时录音+播放场景下稳定性不如 USB 声卡。USB 声卡即插即用，驱动兼容性好。

---

## 2. 系统环境配置

RDK X5 默认运行 Ubuntu 系统（aarch64），Python 3.10+。

```bash
# 确认系统信息
uname -a
# Linux ubuntu 6.1.83 ... aarch64

python3 --version
# Python 3.10.12
```

建议使用清华 pip 镜像源加速下载：

```bash
pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 3. 安装依赖

### 3.1 sherpa-onnx

sherpa-onnx 是由 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 提供的推理框架，原生支持 ARM 架构，集成了 VAD、ASR、TTS 等功能。

```bash
pip3 install sherpa-onnx
```

> **版本说明**：本教程使用 sherpa-onnx 1.12.30，API 可能随版本变化。

sherpa-onnx 自带 ALSA 音频采集接口（`sherpa_onnx.Alsa`），不需要安装 pyaudio。

> **踩坑提醒**：RDK X5 默认没有 `portaudio19-dev`，安装 pyaudio 会失败。直接用 sherpa-onnx 自带的 Alsa 类即可。

### 3.2 edge-tts

```bash
pip3 install edge-tts
```

### 3.3 ffmpeg

```bash
apt-get install -y ffmpeg
```

### 3.4 其他 Python 依赖

```bash
pip3 install numpy
```

---

## 4. 下载模型文件

需要两个模型：

### 4.1 Silero VAD 模型

Silero VAD 是一个极轻量的语音活动检测模型（仅 629KB），非常适合边缘设备。

```bash
mkdir -p models
wget -O models/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
```

### 4.2 SenseVoice ASR 模型

SenseVoice 是阿里达摩院开源的多语言语音识别模型，支持中、英、日、韩、粤五种语言。我们使用 INT8 量化版本（约 229MB），在 RDK X5 上推理速度很快。

```bash
# 从 HuggingFace 下载（如果网络慢，可以用镜像）
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2

# 解压到 models 目录
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2 -C models/
```

> **注意**：在 RDK X5 上从 GitHub 下载速度可能只有 ~700KB/s，229MB 的模型需要耐心等待约 5 分钟。建议提前在电脑上下载好再传到板子上。

最终目录结构：

```
models/
├── silero_vad.onnx                                          (629K)
└── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/
    ├── model.int8.onnx                                      (229M)
    └── tokens.txt
```

---

## 5. 音频设备测试

### 5.1 查看声卡

```bash
aplay -l   # 查看播放设备
arecord -l  # 查看录音设备
```

你应该能看到类似输出：

```
card 0: UACDemoV1.0 [USB audio]
card 1: ES8326 [onboard]
```

### 5.2 测试录音和播放

```bash
# 录制 3 秒音频
arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -d 3 test.wav

# 播放
aplay -D plughw:0,0 test.wav
```

如果能听到自己的声音，说明音频设备工作正常。

> **设备号说明**：`plughw:0,0` 表示第 0 张声卡的第 0 个设备。如果你的 USB 声卡不是 card 0，需要相应调整。

---

## 6. 核心代码详解

### 6.1 VAD — 语音活动检测

VAD 的作用是从连续的音频流中检测出"有人在说话"的片段。我们用 Silero VAD，它的优势是体积小、速度快、准确率高。

```python
import sherpa_onnx

def create_vad():
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = "models/silero_vad.onnx"
    config.silero_vad.threshold = 0.5          # 语音检测阈值
    config.silero_vad.min_silence_duration = 0.5  # 最小静音时长（秒）
    config.silero_vad.min_speech_duration = 0.25  # 最小语音时长（秒）
    config.sample_rate = 16000
    
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    return vad
```

**参数解释：**
- `threshold`：语音概率阈值，越高越严格（减少误触发），越低越灵敏
- `min_silence_duration`：说话停顿多久算"说完了"
- `min_speech_duration`：最短语音段长度，过短的会被过滤掉

**使用方式：**

```python
# 持续喂入音频数据
vad.accept_waveform(audio_chunk)  # float32 numpy array

# 检查是否有完整的语音段
if not vad.empty():
    segment = vad.front       # 获取语音段
    samples = segment.samples # float32 音频数据
    vad.pop()                 # 弹出已处理的段
```

### 6.2 ASR — 语音识别

SenseVoice 支持离线语音识别，在 RDK X5 上使用 INT8 量化模型推理。

```python
def create_asr():
    model_dir = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=f"{model_dir}/model.int8.onnx",
        tokens=f"{model_dir}/tokens.txt",
        language="zh",
        use_itn=True,     # 启用逆文本正则化（数字转阿拉伯数字等）
        num_threads=2,     # 推理线程数
    )
    return recognizer
```

> **重要**：必须使用工厂方法 `from_sense_voice()` 创建识别器，不能直接传 config 构造。这是 sherpa-onnx 针对 SenseVoice 模型的专用接口。

**识别流程：**

```python
import re
import numpy as np

def recognize(recognizer, samples):
    stream = recognizer.create_stream()
    
    # 确保数据是 [-1, 1] 范围的 float32
    normalized = samples.astype(np.float32)
    
    stream.accept_waveform(16000, normalized.tolist())
    recognizer.decode_stream(stream)
    
    text = stream.result.text.strip()
    # SenseVoice 会在结果前加语言/情感标签，需要清除
    text = re.sub(r'<\|[^|]*\|>', '', text).strip()
    return text
```

SenseVoice 的输出格式类似：`<|zh|><|NEUTRAL|><|Speech|>你好世界`，需要用正则清理掉标签。

### 6.3 唤醒词匹配

传统的唤醒词检测需要专用的 KWS（Keyword Spotting）模型。但在 RDK X5 上，我们采用了一个更实用的方案：**VAD + ASR 文本匹配**。

原理很简单：
1. VAD 检测到有人说话
2. ASR 识别出文字
3. 检查文字里是否包含唤醒词

```python
WAKE_PATTERNS = [
    "五五零", "550", "五五〇", "五五领", "五五灵",
    "五五令", "五五另", "wu wu ling", "五50",
]

def is_wake_word(text):
    text_lower = text.lower().replace(" ", "")
    for pattern in WAKE_PATTERNS:
        if pattern.lower().replace(" ", "") in text_lower:
            return True
    return False
```

**为什么要这么多变体？** 因为 ASR 模型对短词的识别不是 100% 准确的，"五五零"可能被识别成"五五领""五五灵"等同音词。列出常见的误识别变体可以大幅提高唤醒成功率。

> **踩坑记录**：我们最初尝试用 sherpa-onnx 的专用 KWS 模型（zipformer transducer），但 GitHub 下载速度太慢（模型很大），最终改用 VAD+ASR 文本匹配方案。实测效果完全够用，而且更灵活 — 改唤醒词只需要改字符串，不需要重新训练模型。

### 6.4 音频采集架构

这是整个系统中最容易出问题的部分。关键设计：

**后台线程持续读取 ALSA 缓冲区：**

```python
import queue

class VoiceAssistant:
    def __init__(self):
        self.alsa = sherpa_onnx.Alsa("plughw:0,0")
        self.is_speaking = False
        self._audio_queue = queue.Queue(maxsize=200)  # ~20 秒缓冲
        
        # 启动后台读取线程
        self._reader_thread = threading.Thread(
            target=self._alsa_reader_loop, daemon=True
        )
        self._reader_thread.start()
    
    def _alsa_reader_loop(self):
        samples_per_read = int(16000 * 0.1)  # 每次读 100ms
        while True:
            samples = self.alsa.read(samples_per_read)
            if self.is_speaking:
                continue  # TTS 播放时丢弃音频，避免自触发
            try:
                self._audio_queue.put_nowait(samples)
            except queue.Full:
                # 队列满了，丢掉最旧的数据
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(samples)
```

**为什么需要后台线程？**

ALSA 的硬件缓冲区是有限的。如果主线程在处理 ASR 或等待 AI 回复时不读取音频数据，ALSA 缓冲区会溢出（overrun），导致后续数据丢失甚至设备错误。

后台线程确保无论主线程在做什么，音频数据都在持续被读取。

**TTS 期间静音处理：**

播放语音回复时，麦克风会采集到扬声器的声音。如果不处理，系统会识别到自己说的话，产生"自触发"。解决方案：

```python
if self.is_speaking:
    continue  # 直接丢弃
```

播放结束后清空队列中残留的音频：

```python
def _drain_queue(self):
    while not self._audio_queue.empty():
        self._audio_queue.get_nowait()
```

### 6.5 TTS — 语音合成

使用 edge-tts 将文字转为语音，再通过 ALSA 播放：

```python
import subprocess
import tempfile

TTS_VOICE = "zh-CN-XiaoyiNeural"  # 微软小伊

def speak(text):
    if not text:
        return
    
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    wav_path = mp3_path.replace(".mp3", ".wav")
    
    try:
        # 1. edge-tts 生成 MP3
        subprocess.run([
            "edge-tts", "--voice", TTS_VOICE,
            "--text", text, "--write-media", mp3_path
        ], capture_output=True, timeout=30)
        
        # 2. ffmpeg 转换为 WAV（ALSA 需要 WAV 格式）
        subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path,
            "-ar", "48000", "-ac", "1", "-f", "wav", wav_path
        ], capture_output=True, timeout=15)
        
        # 3. aplay 播放
        subprocess.run([
            "aplay", "-D", "plughw:0,0", wav_path
        ], capture_output=True, timeout=600)
    finally:
        # 清理临时文件
        for p in [mp3_path, wav_path]:
            try:
                os.unlink(p)
            except:
                pass
```

> **优化技巧**：对于固定的回复（如唤醒回应"在呢"），可以在启动时预生成音频文件缓存，避免每次都调用 edge-tts，大幅减少响应延迟。

### 6.6 完整交互流程

```
┌──────────────────────────────────────────────────────┐
│                   主循环 (listen_loop)                 │
│                                                       │
│  ┌─────────────┐                                     │
│  │ 后台线程持续  │──→ audio_queue ──→ VAD 检测         │
│  │ 读取 ALSA    │                                     │
│  └─────────────┘                                     │
│                                                       │
│  VAD 检测到语音段 → ASR 识别                           │
│       │                                               │
│       ├── 包含唤醒词？                                 │
│       │    ├── 唤醒词后有内容 → 直接处理命令            │
│       │    └── 只有唤醒词 → 回应"在呢" → 等待命令      │
│       │                                               │
│       │    ┌── listen_for_command ──┐                 │
│       │    │  播放"叮"提示音         │                 │
│       │    │  等待用户说话           │                 │
│       │    │  VAD 检测 + ASR 识别    │                 │
│       │    │  播放"咚"结束音         │                 │
│       │    └────────────────────────┘                 │
│       │                                               │
│       └── handle_command                              │
│            │                                          │
│            ├── 发送到 AI 后端                          │
│            ├── 获取回复                                │
│            └── TTS 播放回复                            │
│                                                       │
└──────────────────────────────────────────────────────┘
```

**两种唤醒模式：**

1. **唤醒词 + 命令一起说**：比如"五五零，今天天气怎么样" — 直接识别并处理
2. **先唤醒再说命令**：先说"五五零"，听到"在呢"和提示音后，再说命令

---

## 7. 完整代码

将以下代码保存为 `voice_assistant.py`：

```python
#!/usr/bin/env python3
"""
RDK X5 离线语音助手
- Silero VAD 语音活动检测
- SenseVoice ASR 语音识别
- 唤醒词文本匹配
- edge-tts 语音合成
"""

import os
import sys
import time
import subprocess
import tempfile
import threading
import re
import queue
import numpy as np
import sherpa_onnx

# ── 配置 ──────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
SAMPLE_RATE = 16000
ALSA_DEVICE = "plughw:0,0"
PLAYBACK_DEVICE = "plughw:0,0"
TTS_VOICE = "zh-CN-XiaoyiNeural"

# 唤醒词及其常见误识别变体
WAKE_PATTERNS = [
    "五五零", "550", "五五〇", "五五领", "五五灵",
    "五五令", "五五另", "wu wu ling", "五50",
]

# VAD 参数
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 500
VAD_MIN_SPEECH_MS = 250

# 超时参数
WAKE_LISTEN_TIMEOUT = 15.0   # 唤醒后等待命令的最长时间
POST_SPEECH_SILENCE = 1.5    # 说完话后的静默判定时间


def create_vad():
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = os.path.join(MODELS_DIR, "silero_vad.onnx")
    config.silero_vad.threshold = VAD_THRESHOLD
    config.silero_vad.min_silence_duration = VAD_MIN_SILENCE_MS / 1000.0
    config.silero_vad.min_speech_duration = VAD_MIN_SPEECH_MS / 1000.0
    config.sample_rate = SAMPLE_RATE
    return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)


def create_asr():
    model_dir = os.path.join(
        MODELS_DIR, "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    )
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=os.path.join(model_dir, "model.int8.onnx"),
        tokens=os.path.join(model_dir, "tokens.txt"),
        language="zh",
        use_itn=True,
        num_threads=2,
    )


def recognize(recognizer, samples):
    stream = recognizer.create_stream()
    normalized = samples.astype(np.float32)
    # 如果数据范围不在 [-1, 1]，做归一化
    if float(np.max(np.abs(normalized))) > 1.1:
        normalized = normalized / 32768.0
    stream.accept_waveform(SAMPLE_RATE, normalized.tolist())
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    text = re.sub(r'<\|[^|]*\|>', '', text).strip()
    return text


def is_wake_word(text):
    text_lower = text.lower().replace(" ", "")
    return any(
        p.lower().replace(" ", "") in text_lower
        for p in WAKE_PATTERNS
    )


def extract_command_after_wake(text):
    text_lower = text.lower().replace(" ", "")
    for pattern in WAKE_PATTERNS:
        p = pattern.lower().replace(" ", "")
        idx = text_lower.find(p)
        if idx >= 0:
            remaining = text[idx + len(pattern):].strip().lstrip(",，.。!！?？ ")
            return remaining
    return ""


def speak(text):
    if not text:
        return
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    wav_path = mp3_path.replace(".mp3", ".wav")
    try:
        subprocess.run(
            ["edge-tts", "--voice", TTS_VOICE, "--text", text,
             "--write-media", mp3_path],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path,
             "-ar", "48000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["aplay", "-D", PLAYBACK_DEVICE, wav_path],
            capture_output=True, timeout=600,
        )
    finally:
        for p in [mp3_path, wav_path]:
            try:
                os.unlink(p)
            except OSError:
                pass


def send_to_ai(text):
    """
    将用户指令发送到 AI 后端，获取回复。
    这里需要替换为你自己的 AI 接口调用。
    示例使用 OpenAI 兼容接口：
    """
    # === 替换为你的 AI 调用 ===
    # 最简单的方式：调用本地部署的大模型 API
    # 或者使用 requests 调用远程 API
    #
    # import requests
    # resp = requests.post("http://your-api/v1/chat/completions", json={
    #     "model": "your-model",
    #     "messages": [{"role": "user", "content": text}]
    # })
    # return resp.json()["choices"][0]["message"]["content"]
    
    return f"你说的是：{text}"  # 占位回复，替换为实际 AI 调用


class VoiceAssistant:
    def __init__(self):
        print("[Init] Loading models...")
        self.vad = create_vad()
        self.asr = create_asr()
        self.alsa = sherpa_onnx.Alsa(ALSA_DEVICE)
        self.is_speaking = False
        self._audio_queue = queue.Queue(maxsize=200)

        self._reader_thread = threading.Thread(
            target=self._alsa_reader_loop, daemon=True
        )
        self._reader_thread.start()

        # 预生成唤醒回应音频
        self.wake_wav = "/tmp/wake_response.wav"
        self._prepare_wake_audio()
        print("[Init] Ready! Say the wake word to start.")

    def _alsa_reader_loop(self):
        samples_per_read = int(SAMPLE_RATE * 0.1)
        while True:
            try:
                samples = self.alsa.read(samples_per_read)
                if len(samples) == 0:
                    time.sleep(0.005)
                    continue
                if self.is_speaking:
                    continue
                try:
                    self._audio_queue.put_nowait(samples)
                except queue.Full:
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._audio_queue.put_nowait(samples)
            except Exception as e:
                print(f"[Reader] Error: {e}")
                time.sleep(0.1)

    def _drain_queue(self):
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _prepare_wake_audio(self):
        try:
            mp3_path = "/tmp/wake_response.mp3"
            subprocess.run(
                ["edge-tts", "--voice", TTS_VOICE, "--text", "在呢",
                 "--write-media", mp3_path],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_path, "-ar", "48000",
                 "-ac", "1", "-f", "wav", self.wake_wav],
                capture_output=True, timeout=15,
            )
            os.unlink(mp3_path)
        except Exception as e:
            print(f"[Init] Wake audio failed: {e}")
            self.wake_wav = None

    def _speak_wake(self):
        if self.wake_wav and os.path.exists(self.wake_wav):
            self.is_speaking = True
            try:
                subprocess.run(
                    ["aplay", "-D", PLAYBACK_DEVICE, self.wake_wav],
                    capture_output=True, timeout=10,
                )
            finally:
                self.is_speaking = False
                self._drain_queue()
        else:
            self.is_speaking = True
            speak("在呢")
            self.is_speaking = False
            self._drain_queue()

    def listen_loop(self):
        while True:
            try:
                try:
                    samples = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                arr = np.array(samples, dtype=np.float32)
                self.vad.accept_waveform(arr)

                while not self.vad.empty():
                    segment = self.vad.front
                    audio = np.array(segment.samples, dtype=np.float32).copy()
                    self.vad.pop()

                    if len(audio) < SAMPLE_RATE * 0.3:
                        continue

                    text = recognize(self.asr, audio)
                    if not text:
                        continue

                    print(f"[Heard] {text}")

                    if is_wake_word(text):
                        cmd = extract_command_after_wake(text)
                        if cmd and len(cmd) > 1:
                            self.handle_command(cmd)
                        else:
                            self._speak_wake()
                            self.vad.reset()
                            time.sleep(0.3)
                            self.listen_for_command()

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[Error] {e}")
                time.sleep(0.5)

    def listen_for_command(self):
        print("[Listen] Waiting for command...")
        self._drain_queue()
        self.vad.reset()

        start_time = time.time()
        speech_started = False
        silence_start = None

        while time.time() - start_time < WAKE_LISTEN_TIMEOUT:
            try:
                samples = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                if speech_started and silence_start is None:
                    silence_start = time.time()
                if silence_start and time.time() - silence_start >= POST_SPEECH_SILENCE:
                    break
                continue

            arr = np.array(samples, dtype=np.float32)
            self.vad.accept_waveform(arr)

            energy = float(np.max(np.abs(arr)))
            if energy > 0.05:
                speech_started = True
                silence_start = None
            elif speech_started:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= POST_SPEECH_SILENCE:
                    break

        if not speech_started:
            print("[Listen] No command heard.")
            return

        collected = []
        while not self.vad.empty():
            seg = self.vad.front
            seg_audio = np.array(seg.samples, dtype=np.float32).copy()
            self.vad.pop()
            if len(seg_audio) >= SAMPLE_RATE * 0.3:
                collected.append(seg_audio)

        if not collected:
            return

        audio = np.concatenate(collected)
        text = recognize(self.asr, audio)
        if text:
            self.handle_command(text)

    def handle_command(self, text):
        print(f"[Command] {text}")
        response = send_to_ai(text)
        if response:
            self.is_speaking = True
            speak(response)
            self.is_speaking = False
            self._drain_queue()


def main():
    # 检查模型文件
    vad_model = os.path.join(MODELS_DIR, "silero_vad.onnx")
    sv_dir = os.path.join(
        MODELS_DIR, "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    )
    if not os.path.exists(vad_model):
        print(f"VAD model not found: {vad_model}")
        sys.exit(1)
    if not os.path.exists(sv_dir):
        print(f"SenseVoice model not found: {sv_dir}")
        sys.exit(1)

    assistant = VoiceAssistant()
    assistant.listen_loop()


if __name__ == "__main__":
    main()
```

---

## 8. 运行与测试

### 8.1 直接运行

```bash
python3 voice_assistant.py
```

你应该看到：

```
[Init] Loading models...
[Init] Wake response audio ready.
[Init] Ready! Say the wake word to start.
```

### 8.2 后台运行（推荐）

创建启动脚本 `start.sh`：

```bash
#!/bin/bash
cd "$(dirname "$0")"
echo "Voice assistant launcher (auto-restart on crash)"
while true; do
    echo "[$(date)] Starting voice_assistant.py ..."
    python3 -u voice_assistant.py 2>&1 | tee -a /tmp/voice-assistant.log
    echo "[$(date)] Process exited ($?), restarting in 3s..."
    sleep 3
done
```

```bash
chmod +x start.sh
nohup ./start.sh &
```

### 8.3 测试流程

1. 对着麦克风说"五五零"
2. 听到"在呢"回应
3. 说出你的指令（如"今天天气怎么样"）
4. 等待 AI 回复并语音播放

---

## 9. 常见问题与踩坑记录

### Q: pyaudio 安装失败

```
ERROR: No matching distribution found for pyaudio
```

**A**: RDK X5 缺少 `portaudio19-dev` 依赖。不需要装 pyaudio，直接用 `sherpa_onnx.Alsa`。

### Q: ASR 识别结果有奇怪的标签

识别结果类似：`<|zh|><|NEUTRAL|><|Speech|>你好`

**A**: 这是 SenseVoice 模型的输出格式。用正则清除：

```python
text = re.sub(r'<\|[^|]*\|>', '', text).strip()
```

### Q: 机器人会被自己说的话触发

**A**: 在 TTS 播放时设置 `is_speaking = True`，后台线程检测到这个标志就丢弃采集到的音频。播放结束后清空队列。

### Q: ALSA buffer overrun

```
ALSA lib pcm.c:xxx underrun occurred
```

**A**: 确保后台线程在持续读取音频数据。如果主线程阻塞太久（比如等待 AI 回复），后台线程会继续读取，避免溢出。

### Q: GitHub 下载模型太慢

**A**: 在 RDK X5 上下载 GitHub 文件可能只有 ~700KB/s。建议：
- 在电脑上下载好，用 `scp` 传到板子
- 或使用 HuggingFace 镜像站

### Q: 识别准确率不高

**A**: 检查以下几点：
- 麦克风是否距离太远（建议 50cm 以内）
- 环境噪音是否太大
- USB 声卡的录音增益是否合适（可以用 `alsamixer` 调节）
- VAD threshold 是否需要调整

---

## 10. 进阶优化方向

### 10.1 会话管理

为语音交互添加会话概念 — 一段时间内的对话共享上下文：

```python
SESSION_GAP_SECONDS = 30 * 60  # 30 分钟无交互开启新会话

def get_session_id():
    # 读取上次交互时间
    # 如果间隔 < 30 分钟，复用会话
    # 否则创建新会话
    ...
```

### 10.2 提示音反馈

添加"叮"和"咚"提示音，让用户知道系统什么时候在听：
- "叮" — 开始录音
- "咚" — 录音结束，开始处理

### 10.3 流式 TTS

当前方案是先完整生成回复，再一次性 TTS。可以改为流式：AI 生成一句就 TTS 播放一句，大幅减少等待感。

### 10.4 多语言支持

SenseVoice 本身支持中英日韩粤五种语言，只需修改 `language` 参数或设为自动检测即可。

### 10.5 声纹识别

添加声纹验证，只响应特定用户的唤醒词，避免被其他人误触发。sherpa-onnx 也提供了 speaker identification 相关的模型。

---

## 写在最后

这个项目展示了在 RDK X5 这样的边缘 AI 开发板上，完全可以构建一个实用的离线语音助手。核心的 VAD + ASR 全部在本地运行，响应速度快，不依赖网络。

完整代码和模型都是开源的：
- sherpa-onnx: https://github.com/k2-fsa/sherpa-onnx
- Silero VAD: https://github.com/snakers4/silero-vad
- SenseVoice: https://github.com/FunAudioLLM/SenseVoice
- edge-tts: https://github.com/rany2/edge-tts

如果你也在 RDK X5 或其他 ARM 设备上做语音交互项目，欢迎交流。

---

*本教程基于实际运行在 RDK X5 上的项目编写，所有代码均经过实测验证。*
