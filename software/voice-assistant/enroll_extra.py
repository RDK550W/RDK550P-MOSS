#!/usr/bin/env python3
"""
Supplementary enrollment: record additional short samples to improve accuracy.
Adds to existing speaker profile without replacing old samples.
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


def play_sound(filename):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(path):
        subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, path],
                       capture_output=True, timeout=5)


def speak_tts(text):
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
        print("Usage: python3 enroll_extra.py <name> [num_samples] [duration]")
        sys.exit(1)

    name = sys.argv[1]
    num_samples = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    print(f"[Enroll+] Adding {num_samples} x {duration}s samples for: {name}")

    alsa = sherpa_onnx.Alsa(ALSA_DEVICE)
    sid = SpeakerIdentifier()

    existing = sid.list_speakers()
    print(f"[Enroll+] Current speakers: {existing}")

    prompts = [
        "说一句短话，比如今天天气不错",
        "再说一句，比如帮我查一下日程",
        "换一句，比如现在几点了",
        "再来一句，比如打开空调",
        "最后一句，随便说什么",
        "再说一句短话",
        "继续，换一句",
    ]

    for i in range(num_samples):
        prompt = prompts[i % len(prompts)]
        speak_tts(prompt)
        time.sleep(0.3)
        play_sound("ding.wav")
        print(f"[Enroll+] Recording sample {i+1}/{num_samples}...")
        audio = record(alsa, duration)
        play_sound("dong.wav")

        max_amp = float(np.max(np.abs(audio)))
        print(f"[Enroll+] Sample {i+1}: {len(audio)/SAMPLE_RATE:.1f}s, max_amp={max_amp:.4f}")

        if max_amp < 0.02:
            print(f"[Enroll+] WARNING: nearly silent, skipping")
            continue

        success = sid.enroll_single(name, audio)
        if success:
            print(f"[Enroll+] Sample {i+1} added")
        else:
            print(f"[Enroll+] Sample {i+1} failed")

        if i < num_samples - 1:
            time.sleep(1.5)

    print(f"[Enroll+] Done! Speakers: {sid.list_speakers()}")
    print("ENROLL_EXTRA_OK")


if __name__ == "__main__":
    main()
