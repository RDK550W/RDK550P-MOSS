#!/usr/bin/env python3
"""
Quick speaker enrollment script.
Records 3 samples via ALSA mic and enrolls them.

Usage:
  python3 enroll_speaker.py <name>       # interactive mode (press Enter each time)
  python3 enroll_speaker.py <name> --auto  # auto mode (records immediately)
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speaker_id import SpeakerIdentifier, SAMPLE_RATE

import sherpa_onnx

ALSA_DEVICE = "plughw:0,0"
PLAYBACK_DEVICE = "plughw:0,0"
NUM_SAMPLES = 3
DURATION = 5.0  # seconds per sample


def play_ding():
    """Play ding sound as recording indicator."""
    ding_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ding.wav")
    if os.path.exists(ding_path):
        import subprocess
        subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, ding_path],
                       capture_output=True, timeout=3)


def record(alsa, duration):
    """Record audio from ALSA device."""
    total_samples = int(SAMPLE_RATE * duration)
    collected = []
    chunk_size = int(SAMPLE_RATE * 0.1)  # 100ms

    while len(collected) < total_samples:
        chunk = alsa.read(chunk_size)
        collected.extend(chunk)

    return np.array(collected[:total_samples], dtype=np.float32)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 enroll_speaker.py <name> [--auto]")
        print("Example: python3 enroll_speaker.py YourName")
        sys.exit(1)

    name = sys.argv[1]
    auto_mode = "--auto" in sys.argv

    print(f"=== Speaker Enrollment: {name} ===")
    print(f"Will record {NUM_SAMPLES} samples, {DURATION}s each")
    print(f"Speak naturally in Chinese — read different sentences each time")
    print()

    alsa = sherpa_onnx.Alsa(ALSA_DEVICE)
    sid = SpeakerIdentifier()

    samples_list = []
    for i in range(NUM_SAMPLES):
        print(f"--- Sample {i+1}/{NUM_SAMPLES} ---")
        if auto_mode:
            print(f"Recording in 2 seconds...")
            time.sleep(2)
        else:
            input("Press Enter when ready to speak...")

        play_ding()
        print("Recording... Speak now!")
        audio = record(alsa, DURATION)
        play_ding()

        # Quick check: is there actual speech?
        max_amp = float(np.max(np.abs(audio)))
        print(f"  Recorded: {len(audio)/SAMPLE_RATE:.1f}s, max_amp={max_amp:.4f}")
        if max_amp < 0.05:
            print("  WARNING: Very quiet recording, mic may not be working!")

        samples_list.append(audio)
        print(f"  Sample {i+1} captured!")
        print()

    print("Enrolling...")
    success = sid.enroll(name, samples_list)
    if success:
        print(f"\nDone! '{name}' enrolled successfully.")
        print(f"Enrolled speakers: {sid.list_speakers()}")
    else:
        print(f"\nFailed to enroll '{name}'. Check audio quality.")


if __name__ == "__main__":
    main()
