# 项目知识库 (Knowledge Base)

这是在实际开发和运行 RDK550P-MOSS 过程中积累的技术经验。对复刻者和后续开发非常有价值。

---

## 摄像头

### MIPI 摄像头拍照
- MIPI 摄像头用 `hobot_vio` 的 `libsrcampy.Camera` 拍照，**不是 V4L2**
- 快速拍照：`python3 scripts/snap.py [输出路径]`
- 默认输出到 `media/snapshot.jpg`
- 输出格式 NV12 → OpenCV 转 BGR → JPEG
- 设备节点：`/dev/vin0_cap` ~ `/dev/vin3_cap`

## 语音系统

### 语音助手架构
- 技术栈：sherpa-onnx 1.12.30 + Silero VAD + SenseVoice ASR
- 唤醒词通过 ASR 文本匹配实现（非专用 KWS 模型）— 更灵活、部署更简单
- 完整流程：ALSA 采集 → VAD 检测语音段 → SenseVoice 识别 → 匹配唤醒词 → 录指令 → OpenClaw Agent 处理 → edge-tts 播放回复
- OpenClaw 集成：`openclaw agent --session-id <id> -m <text> --timeout 120`

### TTS 语音合成
- 默认声音：`zh-CN-YunxiNeural`（edge-tts）
- 流程：edge-tts 生成 mp3 → ffmpeg 转 wav → aplay -D plughw:0,0 播放
- `edge-tts --list-voices` 查看所有可用声音

### ALSA 麦克风关键配置
- USB 麦克风（通常识别为 card 0: UACDemoV1.0）**必须开启 AGC**
- AGC 关闭时采集信号极弱（max ~0.03~0.09），VAD 完全失效
- `amixer -c 0 set 'Auto Gain Control' on`
- `amixer -c 0 set 'Mic' 147`
- 静音过滤阈值 max_abs < 0.05（配合 AGC 使用）
- amixer 设置重启可能丢失，需 `alsactl store` 或 systemd ExecStartPre 持久化

### USB 音频模块全双工限制
- plughw:0,0 **不能同时 capture + playback**
- arecord 和 aplay 同时打开同一设备会导致 capture 数据损坏（全零/固定值）
- 解决方案：播放前 kill arecord，播放完后再重启
- 代码中用 `is_speaking` 标志控制，reader 线程重启前检查该标志
- **这是隐蔽 bug** — 不会报错，arecord 正常启动正常读数据，但数据全是无效固定值

### sherpa_onnx.Alsa 已弃用
- 在 RDK X5 + USB 麦克风环境下间歇性返回固定值/陈旧数据
- TTS 播放后尤其容易触发
- 替代方案：`subprocess.Popen` 跑 `arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -t raw`
- reader 线程持续读取 stdout

### sherpa-onnx API 注意事项
- `OfflineRecognizer` 要用工厂方法 `from_sense_voice()`，不能直接传 config
- `OfflineSpeakerDiarizationResult` 在 1.12.30 不能直接迭代
  - 需调 `result.sort_by_start_time()` 返回 list
  - 每个 segment 有 `.speaker` / `.start` / `.end` / `.text` 属性
- KWS 专用模型（zipformer transducer）下载极慢，VAD+ASR 文本匹配更实际

### 声纹识别
- 模型：3dspeaker eres2net base (16k)
- 注册流程：`python3 enroll_speaker.py <名字>` → 对麦克风说几句话 → 存入 speaker_db.json

### 说话人分离 (Speaker Diarization)
- 模块：`voice-assistant/speaker_diarization.py`
- 模型：pyannote segmentation 3.0 (~7MB) + 3dspeaker eres2net（复用声纹识别 embedding）
- API：
  - `SpeakerDiarizer.process()` → 返回分段
  - `process_and_extract()` → 加声纹匹配
  - `segments_to_text()` → 加逐段 ASR
- 完整流程已验证：录音 → 说话人分离 → 声纹识别 → 逐段 ASR
- 离线处理，非实时流式，RDK X5 可跑

## 舵机控制

### 黄金法则
- **必须用 Python 控制，禁止 shell 脚本** — shell 每步 fork bc/sleep 进程开销导致卡顿
- **必须余弦缓动（cosine ease-in-out）** — `(1 - cos(t * pi)) / 2`，起停加速度连续
- **每个动作至少 12~25 步插值** — 步数少于 10 会有明显顿挫感
- **禁止匀速硬切** — 任何移动都要 ease-in-out，没有例外
- PWM 控制通过 sysfs：写 duty_cycle 到 `/sys/class/pwm/pwmchip0/pwmN/duty_cycle`

### 参数参考
- 总行程: yaw ±300000ns（中心 1500000），pitch ±200000ns
- 单个动作 duration: 短动作 0.1~0.18s，长行程 0.2~0.3s
- speed 倍率 1.4~1.8 范围手感最好，可逐轮加速增加节奏感
- 禁止单步跳变超过 300000ns 或无 delay 连续写入
- **标准实现：`scripts/dance.py` 的 `move_eased()` 函数**

### 音乐同步舞蹈编排
- **节奏分析**：
  - Python wave + struct 读取音频（不依赖 librosa）
  - 计算能量包络和 onset 检测找强拍
  - 自相关方法检测 BPM 和节拍周期
  - 生成完整节拍时间线（beat timestamps）
- **同步技术**：
  - 多线程：音乐播放（subprocess）和舞蹈动作（独立线程）同时启动
  - `time.monotonic()` 精确计时，避免累积误差
  - `wait_beat(n)` 函数等到第 n 拍精确时刻再执行
  - 动作时长要考虑缓动插值实际耗时，提前结束以卡准下一拍
- **编舞原则**：
  - 按段落设计（前奏/主歌/副歌/高潮）
  - 强拍大幅度（转身/甩头），弱拍小律动（点头/晃动）
  - 高潮段加快速度和密度
- **参考实现**：`scripts/dance_jntm.py`

## BPU 模型资产

RDK X5 系统自带大量已转换的 BPU 模型（BIN 格式），可直接用 hobot-dnn 推理：

- **路径**：`/opt/hobot/model/x5/basic/` + `/opt/tros/humble/lib/*/config/`
- **目标检测**：YOLOv2/v3/v5s/v8/v10/v11m/v12n, FCOS, CenterNet, SSD MobileNetV1
- **实例分割**：YOLOv8 seg
- **语义分割**：DeepLabV3+, FastSCNN, MobileNet UNet, STDC
- **分类**：MobileNetV1/V2, EfficientNet Lite 0~4, EfficientNASNet, ResNet18, GoogLeNet
- **特殊能力**：YOLO World, DOSOD (开放词汇检测), CLIP, EdgeSAM, MobileSAM
- **推理框架**：hobot-dnn 3.0.1

## 排查经验

### 排查音频问题的正确顺序
1. 先查 ALSA mixer 设置（`amixer -c 0 contents`）
2. 再测直接采集（arecord 录一段看波形）
3. 最后才看代码逻辑
4. **不要一上来就改代码阈值或回退版本**

### 常见陷阱
- pyaudio 在 RDK X5 装不了（无 portaudio19-dev），用 arecord subprocess 替代
- pip 安装慢：用清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple`
- GitHub 下载慢（~700KB/s）：大文件用 hf-mirror.com 或提前下好
- 后台任务超时会被 SIGTERM 杀掉，长时间下载注意 timeout
- ALSA 设备竞争是隐蔽 bug — 不会报错，数据全是固定值，只能通过观察异常发现
