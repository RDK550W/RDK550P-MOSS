#!/usr/bin/env python3
"""
Non-interactive speaker enrollment.
Records 3 x 5s samples with ding prompts, no keyboard input needed.
Designed to be called from the voice assistant session.
"""

import sys
import os
import time
import subprocess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speaker_id import SpeakerIdentifier, SAMPLE_RATE
import sherpa_onnx

ALSA_DEVICE = "plughw:0,0"
PLAYBACK_DEVICE = "plughw:0,0"
NUM_SAMPLES = 3
DURATION = 5.0
PAUSE_BETWEEN = 2.0  # seconds pause between samples


def play_sound(filename):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(path):
        subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, path],
                       capture_output=True, timeout=5)


def speak_tts(text):
    """Quick TTS for prompts."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3 = f.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav = f.name
    try:
        subprocess.run(["edge-tts", "--voice", "zh-CN-XiaoyiNeural", "--text", text,
                         "--write-media", mp3], capture_output=True, timeout=30)
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", "48000", "-ac", "1", "-f", "wav", wav],
                       capture_output=True, timeout=15)
        subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, wav], capture_output=True, timeout=30)
    finally:
        for p in (mp3, wav):
            try:
                os.unlink(p)
            except:
                pass


def record(alsa, duration):
    total = int(SAMPLE_RATE * duration)
    collected = []
    chunk = int(SAMPLE_RATE * 0.1)
    while len(collected) < total:
        samples = alsa.read(chunk)
        collected.extend(samples)
    return np.array(collected[:total], dtype=np.float32)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 enroll_auto.py <name>")
        sys.exit(1)

    name = sys.argv[1]
    print(f"[Enroll] Starting auto enrollment for: {name}")

    alsa = sherpa_onnx.Alsa(ALSA_DEVICE)
    sid = SpeakerIdentifier()

    prompts = [
        f"第一段，请随便说几句话，5秒钟",
        f"第二段，换一句话说",
        f"最后一段，再说点别的",
    ]

    samples_list = []
    for i in range(NUM_SAMPLES):
        speak_tts(prompts[i])
        time.sleep(0.3)
        play_sound("ding.wav")
        print(f"[Enroll] Recording sample {i+1}/{NUM_SAMPLES}...")
        audio = record(alsa, DURATION)
        play_sound("dong.wav")

        max_amp = float(np.max(np.abs(audio)))
        print(f"[Enroll] Sample {i+1}: {len(audio)/SAMPLE_RATE:.1f}s, max_amp={max_amp:.4f}")

        if max_amp < 0.02:
            print(f"[Enroll] WARNING: Sample {i+1} is nearly silent!")

        samples_list.append(audio)

        if i < NUM_SAMPLES - 1:
            time.sleep(PAUSE_BETWEEN)

    print("[Enroll] Processing embeddings...")
    success = sid.enroll(name, samples_list)

    if success:
        print(f"[Enroll] SUCCESS: '{name}' enrolled with {NUM_SAMPLES} samples")
        print(f"[Enroll] All speakers: {sid.list_speakers()}")
        # Output for voice assistant to read
        print(f"ENROLL_OK:{name}")
    else:
        print(f"[Enroll] FAILED for '{name}'")
        print("ENROLL_FAIL")


if __name__ == "__main__":
    main()
