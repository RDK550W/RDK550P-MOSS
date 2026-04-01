#!/usr/bin/env python3
"""
Speaker Identification Module for RDK550P Voice Assistant
Uses sherpa-onnx SpeakerEmbeddingExtractor + 3D-Speaker ERES2Net model.

Features:
- Register speakers with multiple voice samples
- Identify speaker from audio segment
- Persist speaker embeddings to disk (JSON)
- CLI for enrollment and testing
"""

import os
import sys
import json
import numpy as np
import sherpa_onnx

# ── Config ──────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
SPEAKER_MODEL = os.path.join(MODELS_DIR, "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
SPEAKER_DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speaker_db.json")
SAMPLE_RATE = 16000

# Cosine similarity threshold for speaker identification
# Higher = stricter matching, lower = more permissive
SPEAKER_THRESHOLD = 0.35


class SpeakerIdentifier:
    """Speaker identification using sherpa-onnx embedding extractor."""

    def __init__(self, model_path=SPEAKER_MODEL, db_path=SPEAKER_DB_FILE, threshold=SPEAKER_THRESHOLD):
        self.db_path = db_path
        self.threshold = threshold

        # Load embedding model
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig()
        config.model = model_path
        config.num_threads = 2
        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        self.dim = self.extractor.dim

        # Init manager
        self.manager = sherpa_onnx.SpeakerEmbeddingManager(self.dim)

        # Load persisted speakers
        self._load_db()

    def _load_db(self):
        """Load speaker embeddings from JSON file."""
        if not os.path.exists(self.db_path):
            return
        try:
            with open(self.db_path, 'r') as f:
                db = json.load(f)
            self._embeddings_store = db  # keep for persistence
            for name, embeddings in db.items():
                # Pass all embeddings at once so the manager averages them properly
                # (calling add(name, single_emb) multiple times ignores subsequent adds)
                self.manager.add(name, embeddings)
            print(f"[SpeakerID] Loaded {self.manager.num_speakers} speakers from DB")
        except Exception as e:
            print(f"[SpeakerID] Failed to load DB: {e}")

    def _save_db(self):
        """Save all speaker embeddings to JSON file."""
        db = {}
        for name in self.manager.all_speakers:
            # We store embeddings separately during enrollment
            # The manager doesn't expose stored embeddings directly,
            # so we keep our own copy
            pass
        # Use the _embeddings_store for persistence
        if hasattr(self, '_embeddings_store'):
            with open(self.db_path, 'w') as f:
                json.dump(self._embeddings_store, f)
            print(f"[SpeakerID] Saved DB to {self.db_path}")

    def extract_embedding(self, audio_samples):
        """Extract speaker embedding from audio samples.

        Args:
            audio_samples: numpy float32 array, range [-1, 1], 16kHz mono

        Returns:
            list of floats (embedding vector), or None if audio too short
        """
        if len(audio_samples) < SAMPLE_RATE * 0.5:
            print("[SpeakerID] Audio too short for embedding extraction")
            return None

        # Normalize if needed
        samples = np.array(audio_samples, dtype=np.float32)
        max_abs = float(np.max(np.abs(samples)))
        if max_abs > 1.1:
            samples = samples / 32768.0

        stream = self.extractor.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples.tolist())

        if not self.extractor.is_ready(stream):
            print("[SpeakerID] Not enough audio for embedding")
            return None

        embedding = self.extractor.compute(stream)
        return embedding

    def enroll(self, name, audio_samples_list):
        """Enroll a speaker with one or more audio samples.

        Args:
            name: speaker name string
            audio_samples_list: list of numpy float32 arrays (each is one utterance)

        Returns:
            True if enrollment succeeded
        """
        if not hasattr(self, '_embeddings_store'):
            # Load existing store
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, 'r') as f:
                        self._embeddings_store = json.load(f)
                except:
                    self._embeddings_store = {}
            else:
                self._embeddings_store = {}

        embeddings = []
        for samples in audio_samples_list:
            emb = self.extract_embedding(samples)
            if emb is not None:
                embeddings.append(emb)

        if not embeddings:
            print(f"[SpeakerID] No valid embeddings extracted for '{name}'")
            return False

        # Remove old entries if re-enrolling
        if name in self.manager:
            self.manager.remove(name)

        # Register with manager (pass all embeddings at once for averaging)
        success = self.manager.add(name, embeddings)
        if success:
            # Store embeddings for persistence
            self._embeddings_store[name] = embeddings
            self._save_db()
            print(f"[SpeakerID] Enrolled '{name}' with {len(embeddings)} samples")
        else:
            print(f"[SpeakerID] Failed to enroll '{name}'")

        return success

    def enroll_single(self, name, audio_samples):
        """Add a single audio sample to existing speaker enrollment.

        Args:
            name: speaker name
            audio_samples: numpy float32 array

        Returns:
            True if succeeded
        """
        emb = self.extract_embedding(audio_samples)
        if emb is None:
            return False

        if not hasattr(self, '_embeddings_store'):
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, 'r') as f:
                        self._embeddings_store = json.load(f)
                except:
                    self._embeddings_store = {}
            else:
                self._embeddings_store = {}

        # Add to existing embeddings
        if name not in self._embeddings_store:
            self._embeddings_store[name] = []
        self._embeddings_store[name].append(emb)

        # Re-register with manager (clear and re-add all)
        if name in self.manager:
            self.manager.remove(name)
        success = self.manager.add(name, self._embeddings_store[name])

        if success:
            self._save_db()
            print(f"[SpeakerID] Added sample for '{name}' (total: {len(self._embeddings_store[name])})")
        return success

    def update_embedding(self, name, audio_samples, max_embeddings=50):
        """Incrementally update a speaker's voiceprint from usage.
        
        Adds a new embedding extracted from audio. If the total exceeds
        max_embeddings, the oldest embedding is dropped (FIFO).
        Only updates if the audio is long enough and the new embedding
        scores above a minimum threshold (to avoid polluting with noise).

        Args:
            name: enrolled speaker name
            audio_samples: numpy float32 array, 16kHz mono
            max_embeddings: maximum number of embeddings to keep per speaker

        Returns:
            True if embedding was added, False if skipped
        """
        if len(audio_samples) < SAMPLE_RATE * 1.5:
            # Need at least 1.5s of speech for a reliable embedding
            return False

        emb = self.extract_embedding(audio_samples)
        if emb is None:
            return False

        # Verify this embedding actually matches the claimed speaker
        # (safety check — avoid adding wrong-speaker audio)
        if name in self.manager:
            score = self.manager.score(name, emb)
            if score < self.threshold * 0.8:  # slightly lower bar than identification
                print(f"[SpeakerID] Update rejected for '{name}': score={score:.3f} too low")
                return False

        if not hasattr(self, '_embeddings_store'):
            if os.path.exists(self.db_path):
                try:
                    with open(self.db_path, 'r') as f:
                        self._embeddings_store = json.load(f)
                except:
                    self._embeddings_store = {}
            else:
                self._embeddings_store = {}

        if name not in self._embeddings_store:
            self._embeddings_store[name] = []

        self._embeddings_store[name].append(emb)

        # FIFO: drop oldest if over limit
        if len(self._embeddings_store[name]) > max_embeddings:
            dropped = len(self._embeddings_store[name]) - max_embeddings
            self._embeddings_store[name] = self._embeddings_store[name][-max_embeddings:]
            print(f"[SpeakerID] Trimmed {dropped} old embedding(s) for '{name}'")

        # Re-register with manager
        if name in self.manager:
            self.manager.remove(name)
        success = self.manager.add(name, self._embeddings_store[name])

        if success:
            self._save_db()
            total = len(self._embeddings_store[name])
            print(f"[SpeakerID] Updated '{name}' voiceprint (total: {total}/{max_embeddings})")
        return success

    def identify(self, audio_samples):
        """Identify speaker from audio samples.

        Args:
            audio_samples: numpy float32 array

        Returns:
            (name, score) if identified, ("unknown", 0.0) if not
        """
        if self.manager.num_speakers == 0:
            return ("unknown", 0.0)

        emb = self.extract_embedding(audio_samples)
        if emb is None:
            return ("unknown", 0.0)

        name = self.manager.search(emb, self.threshold)
        if name:
            score = self.manager.score(name, emb)
            return (name, score)
        else:
            # Get best score for debugging
            best_name = ""
            best_score = 0.0
            for speaker in self.manager.all_speakers:
                s = self.manager.score(speaker, emb)
                if s > best_score:
                    best_score = s
                    best_name = speaker
            print(f"[SpeakerID] Below threshold. Best: '{best_name}' score={best_score:.3f} (threshold={self.threshold})")
            return ("unknown", best_score)

    def verify(self, name, audio_samples):
        """Verify if audio matches a specific speaker.

        Args:
            name: expected speaker name
            audio_samples: numpy float32 array

        Returns:
            (bool, score)
        """
        emb = self.extract_embedding(audio_samples)
        if emb is None:
            return (False, 0.0)

        if name not in self.manager:
            return (False, 0.0)

        score = self.manager.score(name, emb)
        return (score >= self.threshold, score)

    def list_speakers(self):
        """List all enrolled speakers."""
        return list(self.manager.all_speakers)

    def remove_speaker(self, name):
        """Remove a speaker from the database."""
        if name in self.manager:
            self.manager.remove(name)
        if hasattr(self, '_embeddings_store') and name in self._embeddings_store:
            del self._embeddings_store[name]
            self._save_db()
            return True
        return False

    # ── Unknown Speaker Learning ─────────────────────────────

    def _load_unknown_db(self):
        """Load unknown speaker clusters from disk."""
        if not hasattr(self, '_unknown_db_path'):
            self._unknown_db_path = os.path.join(
                os.path.dirname(self.db_path), "unknown_speakers.json"
            )
        if not hasattr(self, '_unknown_clusters'):
            if os.path.exists(self._unknown_db_path):
                try:
                    with open(self._unknown_db_path, 'r') as f:
                        self._unknown_clusters = json.load(f)
                except Exception:
                    self._unknown_clusters = {}
            else:
                self._unknown_clusters = {}

    def _save_unknown_db(self):
        """Save unknown speaker clusters to disk."""
        self._load_unknown_db()  # ensure path is set
        try:
            with open(self._unknown_db_path, 'w') as f:
                json.dump(self._unknown_clusters, f)
        except Exception as e:
            print(f"[SpeakerID] Failed to save unknown DB: {e}")

    def _cosine_similarity(self, emb_a, emb_b):
        """Compute cosine similarity between two embedding vectors."""
        a = np.array(emb_a, dtype=np.float32)
        b = np.array(emb_b, dtype=np.float32)
        dot = float(np.dot(a, b))
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        if norm < 1e-8:
            return 0.0
        return dot / norm

    def track_unknown(self, audio_samples, merge_threshold=0.55,
                      max_clusters=20, max_embeddings_per_cluster=30,
                      notify_after=5):
        """Track an unknown speaker occurrence.

        Extracts embedding from audio, tries to match against existing
        unknown clusters. If matched, adds to that cluster. If not,
        creates a new cluster.

        Args:
            audio_samples: numpy float32 array, 16kHz mono
            merge_threshold: cosine similarity to merge into existing cluster
            max_clusters: max number of unknown clusters to track
            max_embeddings_per_cluster: max embeddings per cluster
            notify_after: number of occurrences before suggesting enrollment

        Returns:
            dict or None:
                {"cluster_id": str, "count": int, "should_notify": bool}
            None if embedding extraction failed or audio too short.
        """
        if len(audio_samples) < SAMPLE_RATE * 1.0:
            return None

        emb = self.extract_embedding(audio_samples)
        if emb is None:
            return None

        # Make sure it's truly unknown (not matching any enrolled speaker)
        if self.manager.num_speakers > 0:
            name = self.manager.search(emb, self.threshold)
            if name:
                # Actually matches a known speaker, don't track as unknown
                return None

        self._load_unknown_db()

        # Try to match against existing unknown clusters
        best_cluster = None
        best_score = 0.0

        for cid, cluster in self._unknown_clusters.items():
            # Compare against centroid (average of stored embeddings)
            centroid = np.mean(cluster["embeddings"], axis=0).tolist()
            score = self._cosine_similarity(emb, centroid)
            if score > best_score:
                best_score = score
                best_cluster = cid

        if best_cluster and best_score >= merge_threshold:
            # Merge into existing cluster
            cluster = self._unknown_clusters[best_cluster]
            cluster["embeddings"].append(emb)
            cluster["count"] += 1
            cluster["last_seen"] = time.time() if 'time' in dir() else 0
            # Trim oldest embeddings if over limit
            if len(cluster["embeddings"]) > max_embeddings_per_cluster:
                cluster["embeddings"] = cluster["embeddings"][-max_embeddings_per_cluster:]
            self._save_unknown_db()
            should_notify = (cluster["count"] == notify_after)
            print(f"[SpeakerID] Unknown cluster '{best_cluster}' updated "
                  f"(count={cluster['count']}, score={best_score:.3f})")
            return {
                "cluster_id": best_cluster,
                "count": cluster["count"],
                "should_notify": should_notify,
            }
        else:
            # Create new cluster
            # Evict oldest cluster if at capacity
            if len(self._unknown_clusters) >= max_clusters:
                oldest_cid = min(
                    self._unknown_clusters,
                    key=lambda c: self._unknown_clusters[c].get("last_seen", 0)
                )
                del self._unknown_clusters[oldest_cid]
                print(f"[SpeakerID] Evicted oldest unknown cluster '{oldest_cid}'")

            import time as _time
            cid = f"unknown_{int(_time.time()) % 100000}"
            self._unknown_clusters[cid] = {
                "embeddings": [emb],
                "count": 1,
                "last_seen": _time.time(),
                "created": _time.time(),
            }
            self._save_unknown_db()
            print(f"[SpeakerID] New unknown cluster '{cid}' created")
            return {
                "cluster_id": cid,
                "count": 1,
                "should_notify": False,
            }

    def promote_unknown(self, cluster_id, name):
        """Promote an unknown cluster to a registered speaker.

        Args:
            cluster_id: the unknown cluster ID
            name: name to register

        Returns:
            True if succeeded
        """
        self._load_unknown_db()
        if cluster_id not in self._unknown_clusters:
            print(f"[SpeakerID] Unknown cluster '{cluster_id}' not found")
            return False

        embeddings = self._unknown_clusters[cluster_id]["embeddings"]
        if not embeddings:
            return False

        # Register as a known speaker
        if not hasattr(self, '_embeddings_store'):
            self._embeddings_store = {}

        if name in self.manager:
            self.manager.remove(name)

        success = self.manager.add(name, embeddings)
        if success:
            self._embeddings_store[name] = embeddings
            self._save_db()
            # Remove from unknown clusters
            del self._unknown_clusters[cluster_id]
            self._save_unknown_db()
            print(f"[SpeakerID] Promoted unknown cluster '{cluster_id}' -> '{name}' "
                  f"with {len(embeddings)} embeddings")
        return success

    def list_unknown_clusters(self):
        """List unknown speaker clusters with their counts.

        Returns:
            list of dicts: [{"cluster_id": str, "count": int, "created": float}, ...]
        """
        self._load_unknown_db()
        result = []
        for cid, cluster in self._unknown_clusters.items():
            result.append({
                "cluster_id": cid,
                "count": cluster["count"],
                "created": cluster.get("created", 0),
                "last_seen": cluster.get("last_seen", 0),
                "num_embeddings": len(cluster["embeddings"]),
            })
        return sorted(result, key=lambda x: x["count"], reverse=True)

    def clear_unknown_clusters(self):
        """Clear all unknown speaker clusters."""
        self._unknown_clusters = {}
        self._save_unknown_db()
        print("[SpeakerID] Cleared all unknown clusters")


def record_audio_alsa(duration_seconds=3.0, device="plughw:0,0"):
    """Record audio from ALSA device for enrollment.

    Returns:
        numpy float32 array
    """
    alsa = sherpa_onnx.Alsa(device)
    samples_needed = int(SAMPLE_RATE * duration_seconds)
    all_samples = []
    samples_per_read = int(SAMPLE_RATE * 0.1)

    print(f"Recording {duration_seconds}s... Speak now!")
    while len(all_samples) < samples_needed:
        chunk = alsa.read(samples_per_read)
        all_samples.extend(chunk)

    print("Recording done.")
    return np.array(all_samples[:samples_needed], dtype=np.float32)


# ── CLI ──────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Speaker ID management")
    sub = parser.add_subparsers(dest="cmd")

    # Enroll
    p_enroll = sub.add_parser("enroll", help="Enroll a speaker")
    p_enroll.add_argument("name", help="Speaker name")
    p_enroll.add_argument("--samples", type=int, default=3, help="Number of voice samples to record")
    p_enroll.add_argument("--duration", type=float, default=4.0, help="Duration per sample (seconds)")
    p_enroll.add_argument("--device", default="plughw:0,0", help="ALSA device")

    # Identify
    p_id = sub.add_parser("identify", help="Identify speaker from mic")
    p_id.add_argument("--duration", type=float, default=3.0, help="Recording duration")
    p_id.add_argument("--device", default="plughw:0,0", help="ALSA device")

    # List
    sub.add_parser("list", help="List enrolled speakers")

    # Remove
    p_rm = sub.add_parser("remove", help="Remove a speaker")
    p_rm.add_argument("name", help="Speaker name to remove")

    args = parser.parse_args()

    if args.cmd == "enroll":
        sid = SpeakerIdentifier()
        samples_list = []
        for i in range(args.samples):
            print(f"\n--- Sample {i+1}/{args.samples} ---")
            input("Press Enter when ready to speak...")
            audio = record_audio_alsa(args.duration, args.device)
            samples_list.append(audio)
        success = sid.enroll(args.name, samples_list)
        if success:
            print(f"\nEnrolled '{args.name}' successfully!")
        else:
            print(f"\nFailed to enroll '{args.name}'")

    elif args.cmd == "identify":
        sid = SpeakerIdentifier()
        if not sid.list_speakers():
            print("No speakers enrolled. Use 'enroll' first.")
            return
        print("Enrolled speakers:", sid.list_speakers())
        input("Press Enter when ready to speak...")
        audio = record_audio_alsa(args.duration, args.device)
        name, score = sid.identify(audio)
        print(f"\nResult: {name} (score: {score:.3f})")

    elif args.cmd == "list":
        sid = SpeakerIdentifier()
        speakers = sid.list_speakers()
        if speakers:
            print("Enrolled speakers:")
            for s in speakers:
                print(f"  - {s}")
        else:
            print("No speakers enrolled.")

    elif args.cmd == "remove":
        sid = SpeakerIdentifier()
        if sid.remove_speaker(args.name):
            print(f"Removed '{args.name}'")
        else:
            print(f"Speaker '{args.name}' not found")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
