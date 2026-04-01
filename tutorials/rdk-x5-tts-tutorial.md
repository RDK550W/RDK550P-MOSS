# RDK X5 edge-tts 语音合成：让你的机器人开口说话

> 完整实战教程 | edge-tts 安装配置 + 多语言多音色 + ALSA 播放 + 项目集成
> 
> 作者：张晓烨 | D-Robotics 开发者生态
> 
> 硬件平台：地瓜机器人 RDK X5

---

## 你将获得什么

让 RDK X5 开口说话：
- 使用 edge-tts 生成高质量语音（100+ 种音色）
- 通过 ALSA 播放语音
- 封装可复用的 TTS 模块
- 实现语音播报、通知、对话等功能

**为什么选 edge-tts？**
- 免费，无需 API Key
- 音质好（微软 Neural TTS 引擎）
- 支持中文、英文、日文等 100+ 种语言和音色
- 纯 Python 实现，pip 一键安装
- 轻量，不占用 BPU 或 GPU 资源

> **注意**：edge-tts 需要联网（调用微软 Edge 的 TTS 接口）。如果需要完全离线的 TTS，可以考虑 sherpa-onnx 的离线 TTS 模型。

---

## 目录

1. [安装与配置](#1-安装与配置)
2. [快速体验](#2-快速体验)
3. [音色选择](#3-音色选择)
4. [ALSA 音频播放](#4-alsa-音频播放)
5. [完整 TTS 模块](#5-完整-tts-模块)
6. [进阶用法](#6-进阶用法)
   - 6.1 语速/音调调节
   - 6.2 SSML 标记
   - 6.3 流式生成
   - 6.4 缓存优化
7. [项目集成示例](#7-项目集成示例)
8. [常见问题](#8-常见问题)

---

## 1. 安装与配置

### 安装 edge-tts

```bash
pip3 install edge-tts
```

### 安装 ffmpeg（音频格式转换）

```bash
apt-get install -y ffmpeg
```

### 确认 ALSA 播放设备

```bash
aplay -l
```

记住你的 USB 声卡设备号，例如 `plughw:0,0`。

---

## 2. 快速体验

### 命令行方式

```bash
# 生成语音文件
edge-tts --voice zh-CN-XiaoyiNeural --text "你好，我是RDK X5机器人" --write-media hello.mp3

# 转换格式（aplay 需要 WAV）
ffmpeg -y -i hello.mp3 -ar 48000 -ac 1 -f wav hello.wav

# 播放
aplay -D plughw:0,0 hello.wav
```

### Python 方式

```python
import subprocess

text = "你好，我是RDK X5机器人"
voice = "zh-CN-XiaoyiNeural"

# 生成 + 转换 + 播放
subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", "/tmp/tts.mp3"])
subprocess.run(["ffmpeg", "-y", "-i", "/tmp/tts.mp3", "-ar", "48000", "-ac", "1", "-f", "wav", "/tmp/tts.wav"])
subprocess.run(["aplay", "-D", "plughw:0,0", "/tmp/tts.wav"])
```

---

## 3. 音色选择

### 列出所有可用音色

```bash
edge-tts --list-voices
```

### 推荐中文音色

| 音色 ID | 性别 | 风格 | 推荐场景 |
|---------|------|------|---------|
| `zh-CN-XiaoyiNeural` | 女 | 温暖亲切 | 日常对话、助手 |
| `zh-CN-YunxiNeural` | 男 | 年轻自然 | 日常对话、助手 |
| `zh-CN-YunjianNeural` | 男 | 沉稳专业 | 新闻播报、正式场合 |
| `zh-CN-XiaoxiaoNeural` | 女 | 活泼开朗 | 故事讲述、娱乐 |
| `zh-CN-YunyangNeural` | 男 | 新闻播音 | 播报、通知 |

### 英文音色

| 音色 ID | 性别 | 风格 |
|---------|------|------|
| `en-US-JennyNeural` | 女 | 自然流畅 |
| `en-US-GuyNeural` | 男 | 沉稳 |
| `en-GB-SoniaNeural` | 女 | 英式英语 |

### 试听和选择

```python
import subprocess

voices = [
    ("zh-CN-XiaoyiNeural", "小伊"),
    ("zh-CN-YunxiNeural", "云希"),
    ("zh-CN-XiaoxiaoNeural", "晓晓"),
]

for voice_id, name in voices:
    print(f"正在播放: {name} ({voice_id})")
    subprocess.run(["edge-tts", "--voice", voice_id,
                    "--text", f"你好，我是{name}，很高兴认识你",
                    "--write-media", "/tmp/test_voice.mp3"],
                   capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", "/tmp/test_voice.mp3",
                    "-ar", "48000", "-ac", "1", "-f", "wav",
                    "/tmp/test_voice.wav"],
                   capture_output=True)
    subprocess.run(["aplay", "-D", "plughw:0,0", "/tmp/test_voice.wav"],
                   capture_output=True)
    import time
    time.sleep(0.5)
```

---

## 4. ALSA 音频播放

### 为什么需要格式转换？

edge-tts 输出 MP3 格式，但 ALSA 的 `aplay` 只支持 WAV/PCM。需要用 ffmpeg 转换。

### 播放参数

```bash
aplay -D plughw:0,0 output.wav
```

- `-D plughw:0,0`：指定播放设备
- `plughw` 会自动做采样率转换，比 `hw` 更兼容

### 调节音量

```bash
# 安装 alsa-utils（通常已预装）
alsamixer
# 选择声卡，调节 Master/Speaker 音量
```

或命令行：

```bash
amixer -c 0 set Master 80%
```

---

## 5. 完整 TTS 模块

一个可直接集成到项目中的 TTS 模块：

```python
#!/usr/bin/env python3
"""
RDK X5 TTS 模块
使用 edge-tts + ffmpeg + ALSA 实现语音合成和播放
"""
import os
import subprocess
import tempfile
import hashlib


class TTS:
    """语音合成器"""
    
    def __init__(self, voice="zh-CN-XiaoyiNeural", device="plughw:0,0",
                 cache_dir="/tmp/tts_cache"):
        self.voice = voice
        self.device = device
        self.cache_dir = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
    
    def speak(self, text, block=True):
        """
        合成并播放语音
        Args:
            text: 要朗读的文本
            block: 是否阻塞等待播放完成
        """
        if not text or not text.strip():
            return
        
        wav_path = self._get_or_generate(text)
        if wav_path is None:
            return
        
        cmd = ["aplay", "-D", self.device, wav_path]
        if block:
            subprocess.run(cmd, capture_output=True, timeout=600)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    
    def generate(self, text, output_path):
        """只生成 WAV 文件，不播放"""
        mp3_path = output_path + ".mp3"
        try:
            subprocess.run(
                ["edge-tts", "--voice", self.voice,
                 "--text", text, "--write-media", mp3_path],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_path,
                 "-ar", "48000", "-ac", "1", "-f", "wav", output_path],
                capture_output=True, timeout=15,
            )
            return True
        except Exception as e:
            print(f"[TTS Error] {e}")
            return False
        finally:
            try:
                os.unlink(mp3_path)
            except OSError:
                pass
    
    def _get_or_generate(self, text):
        """带缓存的语音生成"""
        if self.cache_dir:
            # 基于文本和音色生成缓存 key
            key = hashlib.md5(
                f"{self.voice}:{text}".encode()
            ).hexdigest()[:12]
            wav_path = os.path.join(self.cache_dir, f"{key}.wav")
            
            if os.path.exists(wav_path):
                return wav_path
        else:
            wav_path = tempfile.mktemp(suffix=".wav")
        
        if self.generate(text, wav_path):
            return wav_path
        return None
    
    def clear_cache(self):
        """清除缓存"""
        if self.cache_dir and os.path.exists(self.cache_dir):
            for f in os.listdir(self.cache_dir):
                if f.endswith(".wav"):
                    os.unlink(os.path.join(self.cache_dir, f))


# 使用示例
if __name__ == "__main__":
    tts = TTS(voice="zh-CN-XiaoyiNeural")
    
    # 基本使用
    tts.speak("你好，我是RDK X5机器人")
    
    # 第二次调用同样文本会使用缓存，瞬间播放
    tts.speak("你好，我是RDK X5机器人")
    
    # 切换音色
    tts_male = TTS(voice="zh-CN-YunxiNeural")
    tts_male.speak("你好，我是男声助手")
    
    # 非阻塞播放
    tts.speak("这句话在后台播放", block=False)
    print("主线程继续执行...")
```

---

## 6. 进阶用法

### 6.1 语速和音调调节

```bash
# 加速 20%
edge-tts --voice zh-CN-XiaoyiNeural --rate="+20%" --text "说话加速" --write-media fast.mp3

# 减速 30%
edge-tts --voice zh-CN-XiaoyiNeural --rate="-30%" --text "说话减速" --write-media slow.mp3

# 提高音调
edge-tts --voice zh-CN-XiaoyiNeural --pitch="+10Hz" --text "声音变高" --write-media high.mp3
```

Python 中：

```python
subprocess.run([
    "edge-tts",
    "--voice", "zh-CN-XiaoyiNeural",
    "--rate", "+15%",       # 语速
    "--pitch", "+5Hz",      # 音调
    "--volume", "+20%",     # 音量
    "--text", "调整后的语音",
    "--write-media", "/tmp/adjusted.mp3"
])
```

### 6.2 SSML 标记语言

对于需要精细控制的场景，可以使用 SSML：

```python
import asyncio
import edge_tts

async def ssml_speak():
    ssml = """
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">
        <voice name="zh-CN-XiaoyiNeural">
            <prosody rate="medium" pitch="medium">
                你好！
                <break time="500ms"/>
                欢迎来到RDK X5的世界。
                <emphasis level="strong">这是重点内容。</emphasis>
            </prosody>
        </voice>
    </speak>
    """
    communicate = edge_tts.Communicate(ssml, voice="zh-CN-XiaoyiNeural")
    await communicate.save("/tmp/ssml_output.mp3")

asyncio.run(ssml_speak())
```

### 6.3 流式生成

对于长文本，可以流式生成并逐段播放，减少首次响应延迟：

```python
import asyncio
import edge_tts

async def stream_tts(text, voice="zh-CN-XiaoyiNeural"):
    communicate = edge_tts.Communicate(text, voice)
    
    with open("/tmp/stream.mp3", "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])

asyncio.run(stream_tts("这是一段很长的文本，流式生成可以更快开始播放。"))
```

### 6.4 缓存优化

对于固定的语音（如提示音、欢迎语），在启动时预生成缓存：

```python
# 启动时预缓存常用语音
PRELOAD_PHRASES = [
    "在呢",
    "好的",
    "收到",
    "正在处理",
    "完成了",
    "抱歉，我没听清",
]

tts = TTS()
for phrase in PRELOAD_PHRASES:
    tts._get_or_generate(phrase)  # 预生成缓存

print("常用语音已缓存，后续播放无延迟")
```

---

## 7. 项目集成示例

### 天气播报

```python
def announce_weather(tts, weather_info):
    text = f"今天{weather_info['city']}的天气{weather_info['condition']}，" \
           f"气温{weather_info['temp_low']}到{weather_info['temp_high']}度。"
    if "雨" in weather_info['condition']:
        text += "记得带伞。"
    tts.speak(text)
```

### 定时提醒

```python
import time
from datetime import datetime

tts = TTS()

reminders = [
    ("10:00", "该站起来活动一下了"),
    ("12:00", "午饭时间到了"),
    ("18:00", "下班时间到了，辛苦了"),
]

while True:
    now = datetime.now().strftime("%H:%M")
    for reminder_time, message in reminders:
        if now == reminder_time:
            tts.speak(message)
    time.sleep(60)
```

### 语音交互助手

```python
# 语音助手中的 TTS 集成
class VoiceAssistant:
    def __init__(self):
        self.tts = TTS(voice="zh-CN-XiaoyiNeural")
        # ... 其他初始化 ...
    
    def respond(self, ai_reply):
        """播放 AI 回复"""
        # 清理 markdown 格式（TTS 不需要）
        clean_text = ai_reply.replace("**", "").replace("*", "")
        clean_text = clean_text.replace("#", "").replace("`", "")
        
        # 截取最后一段（避免播放太长）
        if "\n" in clean_text:
            clean_text = clean_text.split("\n")[-1]
        
        self.tts.speak(clean_text)
```

---

## 8. 常见问题

### Q: edge-tts 报网络错误

**A**: edge-tts 需要联网。检查网络连接：
```bash
ping -c 3 speech.platform.bing.com
```
如果网络不可用，考虑使用 sherpa-onnx 的离线 TTS。

### Q: 播放有杂音或卡顿

**A**: 
- 检查 USB 声卡连接是否稳固
- 尝试调整采样率：`-ar 44100` 或 `-ar 16000`
- 避免同时录音和播放

### Q: 如何减少首次播放延迟？

**A**: 三个策略：
1. **预缓存**：启动时预生成常用语音
2. **降低采样率**：`-ar 16000` 比 `-ar 48000` 文件更小
3. **流式处理**：边生成边播放（需要用 async API）

### Q: 中英文混合怎么办？

**A**: edge-tts 支持中英文混合朗读，无需特殊处理：
```python
tts.speak("今天的temperature是25度，very comfortable")
```

### Q: 能否完全离线？

**A**: edge-tts 本身不支持离线。离线方案：
- sherpa-onnx 的离线 TTS 模型（中文可用 vits-zh）
- piper TTS（开源离线方案）
- 预生成所有可能的语音并缓存

---

*本教程基于 RDK X5 实际开发经验编写，代码经过实测验证。*
