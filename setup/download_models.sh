#!/bin/bash
# 下载 RDK550P-MOSS 所需的 AI 模型
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/voice-assistant/models"
mkdir -p "$MODEL_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }

# --- Silero VAD ---
SILERO_URL="https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
SILERO_FILE="$MODEL_DIR/silero_vad.onnx"
if [ -f "$SILERO_FILE" ]; then
    info "Silero VAD 已存在，跳过"
else
    info "下载 Silero VAD..."
    wget -q --show-progress -O "$SILERO_FILE" "$SILERO_URL" || {
        warn "GitHub 下载失败，尝试 HuggingFace 镜像..."
        wget -q --show-progress -O "$SILERO_FILE" \
            "https://hf-mirror.com/k2-fsa/sherpa-onnx-vad-models/resolve/main/silero_vad.onnx"
    }
fi

# --- SenseVoice ASR ---
SENSE_DIR="$MODEL_DIR/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
SENSE_MODEL="$SENSE_DIR/model.int8.onnx"
if [ -f "$SENSE_MODEL" ]; then
    info "SenseVoice ASR 已存在，跳过"
else
    info "下载 SenseVoice ASR (~229MB)..."
    SENSE_TAR="$MODEL_DIR/sensevoice.tar.bz2"

    # 尝试 HuggingFace 镜像（国内更快）
    wget -q --show-progress -O "$SENSE_TAR" \
        "https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2" \
    || wget -q --show-progress -O "$SENSE_TAR" \
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"

    info "解压 SenseVoice..."
    tar -xjf "$SENSE_TAR" -C "$MODEL_DIR/"
    rm -f "$SENSE_TAR"
fi

# --- 3D-Speaker (声纹识别) ---
SPEAKER_FILE="$MODEL_DIR/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
if [ -f "$SPEAKER_FILE" ]; then
    info "3D-Speaker 声纹模型已存在，跳过"
else
    info "下载 3D-Speaker 声纹识别模型..."
    wget -q --show-progress -O "$SPEAKER_FILE" \
        "https://hf-mirror.com/csukuangfj/3dspeaker/resolve/main/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" \
    || wget -q --show-progress -O "$SPEAKER_FILE" \
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
fi

# --- Pyannote Segmentation 3.0 (说话人分离，可选) ---
PYANNOTE_DIR="$MODEL_DIR/sherpa-onnx-pyannote-segmentation-3-0"
PYANNOTE_MODEL="$PYANNOTE_DIR/model.onnx"
if [ -f "$PYANNOTE_MODEL" ]; then
    info "Pyannote 分割模型已存在，跳过"
else
    info "下载 Pyannote Segmentation 3.0 (~7MB)..."
    PYANNOTE_TAR="$MODEL_DIR/pyannote-seg.tar.bz2"

    wget -q --show-progress -O "$PYANNOTE_TAR" \
        "https://hf-mirror.com/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" \
    || wget -q --show-progress -O "$PYANNOTE_TAR" \
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"

    tar -xjf "$PYANNOTE_TAR" -C "$MODEL_DIR/"
    rm -f "$PYANNOTE_TAR"
fi

echo ""
info "所有模型下载完成！"
du -sh "$MODEL_DIR"
