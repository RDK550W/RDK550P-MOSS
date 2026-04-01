#!/usr/bin/env python3
"""
Speaker Diarization Module for RDK550P Voice Assistant
Uses sherpa-onnx OfflineSpeakerDiarization with:
  - pyannote segmentation model (segment audio into speaker turns)
  - 3D-Speaker ERES2Net embedding model (reused from speaker_id)

Given an audio buffer, returns a list of (speaker_label, start_sec, end_sec) segments.
When combined with SpeakerIdentifier, maps cluster labels to enrolled names.
"""

import os
import numpy as np
import sherpa_onnx

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
SEGMENTATION_MODEL = os.path.join(
    MODELS_DIR, "sherpa-onnx-pyannote-segmentation-3-0", "model.onnx"
)
EMBEDDING_MODEL = os.path.join(
    MODELS_DIR, "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)
SAMPLE_RATE = 16000


class SpeakerDiarizer:
    """Offline speaker diarization using sherpa-onnx."""

    def __init__(
        self,
        segmentation_model=SEGMENTATION_MODEL,
        embedding_model=EMBEDDING_MODEL,
        num_clusters=0,  # 0 = auto-detect number of speakers
        threshold=0.35,  # clustering threshold (lower = more likely to split speakers)
        num_threads=2,
    ):
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=segmentation_model,
                ),
                num_threads=num_threads,
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=embedding_model,
                num_threads=num_threads,
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=num_clusters,
                threshold=threshold,
            ),
            min_duration_on=0.2,   # keep shorter speech segments
            min_duration_off=0.2,  # keep shorter gaps between segments
        )

        if not config.validate():
            raise RuntimeError("Invalid diarization config")

        self.sd = sherpa_onnx.OfflineSpeakerDiarization(config)
        self.sample_rate = self.sd.sample_rate
        print(f"[Diarization] Loaded. Expected sample_rate={self.sample_rate}")

    def process(self, audio_samples):
        """Run diarization on audio samples.

        Args:
            audio_samples: numpy float32 array, range [-1, 1], 16kHz mono

        Returns:
            list of dicts: [{"speaker": int, "start": float, "end": float}, ...]
            Speaker labels are integer cluster IDs (0, 1, 2, ...).
        """
        samples = np.array(audio_samples, dtype=np.float32)

        # Normalize if needed
        max_abs = float(np.max(np.abs(samples)))
        if max_abs > 1.1:
            samples = samples / 32768.0

        result = self.sd.process(samples.tolist())

        segments = []
        for seg in result.sort_by_start_time():
            segments.append({
                "speaker": seg.speaker,
                "start": seg.start,
                "end": seg.end,
            })

        return segments

    def process_and_extract(self, audio_samples, speaker_identifier=None):
        """Run diarization and optionally map cluster IDs to enrolled speaker names.

        Args:
            audio_samples: numpy float32 array
            speaker_identifier: optional SpeakerIdentifier instance for name mapping

        Returns:
            list of dicts: [{"speaker": str, "start": float, "end": float}, ...]
            If speaker_identifier is provided, speaker field will be enrolled name
            or "未知说话人_N" for unknown speakers.
        """
        samples = np.array(audio_samples, dtype=np.float32)
        max_abs = float(np.max(np.abs(samples)))
        if max_abs > 1.1:
            samples = samples / 32768.0

        segments = self.process(samples)
        if not segments or speaker_identifier is None:
            # Convert int speaker IDs to string labels
            for seg in segments:
                seg["speaker"] = f"说话人{seg['speaker']}"
            return segments

        # Map cluster IDs to enrolled names using embedding comparison
        # Extract representative audio for each cluster and identify
        cluster_ids = set(seg["speaker"] for seg in segments)
        cluster_name_map = {}

        for cid in cluster_ids:
            # Collect all audio for this cluster
            cluster_audio_parts = []
            for seg in segments:
                if seg["speaker"] == cid:
                    start_sample = int(seg["start"] * SAMPLE_RATE)
                    end_sample = int(seg["end"] * SAMPLE_RATE)
                    start_sample = max(0, start_sample)
                    end_sample = min(len(samples), end_sample)
                    if end_sample > start_sample:
                        cluster_audio_parts.append(samples[start_sample:end_sample])

            if not cluster_audio_parts:
                cluster_name_map[cid] = f"未知说话人_{cid}"
                continue

            # Use the longest segment for identification (most reliable)
            best_audio = max(cluster_audio_parts, key=len)

            try:
                name, score = speaker_identifier.identify(best_audio)
                if name != "unknown":
                    cluster_name_map[cid] = name
                    print(f"[Diarization] Cluster {cid} -> {name} (score={score:.3f})")
                else:
                    cluster_name_map[cid] = f"未知说话人_{cid}"
                    print(f"[Diarization] Cluster {cid} -> unknown (best_score={score:.3f})")
            except Exception as e:
                print(f"[Diarization] Error identifying cluster {cid}: {e}")
                cluster_name_map[cid] = f"未知说话人_{cid}"

        # Apply name mapping
        for seg in segments:
            seg["speaker"] = cluster_name_map.get(seg["speaker"], f"未知说话人_{seg['speaker']}")

        return segments


def segments_to_text(segments, audio_samples, asr_recognizer):
    """Run ASR on each diarization segment and format as "speaker: text".

    Args:
        segments: list of dicts from process_and_extract()
        audio_samples: original audio numpy array
        asr_recognizer: sherpa-onnx OfflineRecognizer instance

    Returns:
        str: formatted text like "Leaf: 你好\n未知说话人_1: 你也好"
    """
    import re as _re

    samples = np.array(audio_samples, dtype=np.float32)
    max_abs = float(np.max(np.abs(samples)))
    if max_abs > 1.1:
        samples = samples / 32768.0

    lines = []
    for seg in segments:
        start_sample = int(seg["start"] * SAMPLE_RATE)
        end_sample = int(seg["end"] * SAMPLE_RATE)
        start_sample = max(0, start_sample)
        end_sample = min(len(samples), end_sample)

        if end_sample - start_sample < SAMPLE_RATE * 0.3:
            continue  # too short for ASR

        seg_audio = samples[start_sample:end_sample]

        # Run ASR on this segment
        stream = asr_recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, seg_audio.tolist())
        asr_recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        # Strip SenseVoice tags
        text = _re.sub(r'<\|[^|]*\|>', '', text).strip()

        if text:
            lines.append(f"{seg['speaker']}: {text}")

    return "\n".join(lines)


# ── Quick test CLI ──────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import wave

    if len(sys.argv) < 2:
        print("Usage: python3 speaker_diarization.py <audio.wav> [--identify]")
        print("  --identify: also map speakers to enrolled names")
        sys.exit(1)

    wav_path = sys.argv[1]
    do_identify = "--identify" in sys.argv

    # Read wav file
    with wave.open(wav_path, 'r') as wf:
        assert wf.getsampwidth() == 2, "Only 16-bit WAV supported"
        assert wf.getnchannels() == 1, "Only mono WAV supported"
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != SAMPLE_RATE:
        print(f"Warning: sample rate is {sr}, expected {SAMPLE_RATE}")

    diarizer = SpeakerDiarizer()

    if do_identify:
        from speaker_id import SpeakerIdentifier
        sid = SpeakerIdentifier()
        segments = diarizer.process_and_extract(audio, speaker_identifier=sid)
    else:
        segments = diarizer.process(audio)
        for seg in segments:
            seg["speaker"] = f"说话人{seg['speaker']}"

    print(f"\n=== Diarization Results ({len(segments)} segments) ===")
    for seg in segments:
        print(f"  [{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['speaker']}")
