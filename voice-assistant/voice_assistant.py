#!/usr/bin/env python3
"""
RDK550P Voice Assistant
- Continuous listening via ALSA microphone
- Silero VAD for speech detection
- SenseVoice ASR for speech recognition
- Wake word: "五五零" / "550" variants
- OpenClaw integration for AI responses
- edge-tts + aplay for voice output
"""

import os
import sys
import json
import time
import subprocess
import tempfile
import threading
import re
import queue
import numpy as np
import sherpa_onnx

# Speaker identification (optional — graceful fallback if model missing)
try:
    from speaker_id import SpeakerIdentifier
    _SPEAKER_ID_AVAILABLE = True
except ImportError:
    _SPEAKER_ID_AVAILABLE = False

# Speaker diarization (optional — graceful fallback if model missing)
try:
    from speaker_diarization import SpeakerDiarizer, segments_to_text
    _DIARIZATION_AVAILABLE = True
except ImportError:
    _DIARIZATION_AVAILABLE = False

# ── Config ──────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
SAMPLE_RATE = 16000
CHANNELS = 1
ALSA_DEVICE = "plughw:0,0"  # USB audio
PLAYBACK_DEVICE = "plughw:0,0"
TTS_VOICE = "zh-CN-XiaoyiNeural"

# Wake word patterns (fuzzy match)
WAKE_PATTERNS = [
    "五五零", "550", "五五〇", "五五领", "五五灵",
    "五五令", "五五另", "wu wu ling", "五50",
    "五五零批", "550p", "五五零p",
    "五零", "50", "五〇", "五领", "五灵", "五令",
    "wuling", "wu ling", "物理", "物0", "物流", "5林"
]

# VAD config
VAD_THRESHOLD = 0.5
VAD_MIN_SILENCE_MS = 500
VAD_MIN_SPEECH_MS = 250
VAD_WINDOW_SIZE = 512  # 32ms at 16kHz

# Timeouts
WAKE_LISTEN_TIMEOUT = 10.0  # seconds to listen for command after wake
POST_SPEECH_SILENCE = 1.5  # seconds of silence to end recording

def create_vad():
    """Create Silero VAD instance."""
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = os.path.join(MODELS_DIR, "silero_vad.onnx")
    config.silero_vad.threshold = VAD_THRESHOLD
    config.silero_vad.min_silence_duration = VAD_MIN_SILENCE_MS / 1000.0
    config.silero_vad.min_speech_duration = VAD_MIN_SPEECH_MS / 1000.0
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
    return vad


def create_asr():
    """Create SenseVoice offline recognizer."""
    model_dir = os.path.join(MODELS_DIR, "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=os.path.join(model_dir, "model.int8.onnx"),
        tokens=os.path.join(model_dir, "tokens.txt"),
        language="zh",
        use_itn=True,
        num_threads=2,
    )
    return recognizer


def recognize(recognizer, samples):
    """Run ASR on audio samples (float32 numpy array, expected range [-1, 1])."""
    stream = recognizer.create_stream()
    # sherpa-onnx accept_waveform expects normalized float32 in [-1, 1]
    # Alsa.read() already returns normalized floats, so pass through directly.
    # If somehow we get int16-range values, normalize them down.
    max_abs = float(np.max(np.abs(samples)))
    if max_abs > 1.1:
        normalized = (samples / 32768.0).astype(np.float32)
    else:
        normalized = samples.astype(np.float32)
    print(f"[Debug ASR] len={len(normalized)}, orig_max={max_abs:.4f}, norm_max={float(np.max(np.abs(normalized))):.4f}")
    stream.accept_waveform(SAMPLE_RATE, normalized.tolist())
    recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    print(f"[Debug ASR] result: '{text}'")
    # SenseVoice may prefix with language/emotion tags like <|zh|><|NEUTRAL|><|Speech|>
    text = re.sub(r'<\|[^|]*\|>', '', text).strip()
    return text


def is_wake_word(text):
    """Check if text contains wake word."""
    text_lower = text.lower().replace(" ", "")
    for pattern in WAKE_PATTERNS:
        if pattern.lower().replace(" ", "") in text_lower:
            return True
    return False


def extract_command_after_wake(text):
    """Extract command portion after wake word, if any."""
    text_lower = text.lower().replace(" ", "")
    for pattern in WAKE_PATTERNS:
        p = pattern.lower().replace(" ", "")
        idx = text_lower.find(p)
        if idx >= 0:
            # Get the part after the wake word in original text
            # Approximate position
            remaining = text[idx + len(pattern):]
            remaining = remaining.strip().lstrip(",，.。!！?？ ")
            return remaining
    return ""


def speak(text):
    """TTS and play audio (optimized: direct wav output)."""
    if not text:
        return
    # Agent uses [output] marker to control what gets spoken
    # If multiple [output] markers exist, only speak the content after the LAST one
    if '[output]' in text:
        text = text.split('[output]')[-1].strip()
    if not text:
        return
    # Merge multiple lines into one sentence for natural speech
    text = " ".join(line.strip() for line in text.split('\n') if line.strip())
    # Strip any remaining markdown artifacts
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^#+\s*', '', text)
    text = re.sub(r'^[-*]\s+', '', text)
    if not text:
        return
    print(f"[TTS] Speaking: {text}")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        # edge-tts outputs mp3 regardless of extension, must convert to wav for aplay
        subprocess.run(
            ["edge-tts", "--voice", TTS_VOICE, "--text", text, "--write-media", mp3_path],
            capture_output=True, timeout=30
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "48000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True, timeout=15
        )
        subprocess.run(
            ["aplay", "-D", PLAYBACK_DEVICE, wav_path],
            capture_output=True, timeout=600
        )
    except Exception as e:
        print(f"[TTS Error] {e}")
    finally:
        for p in (mp3_path, wav_path):
            try:
                os.unlink(p)
            except:
                pass


VOICE_CTX_PREFIX = \
    "[系统提示：你正处于语音TTS/STT交互模式。用户通过麦克风说话，经语音识别后文字发给你；" \
    "你的回复会经过 text.split('[output]')[-1] 处理后由TTS朗读给用户。" \
    "规则：1）在你最终想让用户听到的内容前面加[output]标记；" \
    "2）如果需要执行工具/脚本，执行完毕后在最终回复前再加一个[output]；" \
    "3）用自然口语表达，不要markdown格式，简洁直接。] 用户说："



# Session state file for auto-rotating voice session ID based on conversation gap.
SESSION_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_state.json")
SESSION_GAP_SECONDS = 30 * 60  # Start a new session after 30min of inactivity


def get_voice_session_id():
    """Return session ID to use for this query.
    Reuses the current session if last activity was within SESSION_GAP_SECONDS,
    otherwise starts a fresh session (new timestamp-based ID).
    """
    now = int(time.time())
    try:
        with open(SESSION_STATE_FILE, "r") as f:
            state = json.load(f)
        last_active = state.get("last_active", 0)
        session_id = state.get("session_id", "")
        if session_id and (now - last_active) < SESSION_GAP_SECONDS:
            # Still within active conversation window — reuse
            print(f"[Session] Reusing session: {session_id} (gap {now - last_active}s < {SESSION_GAP_SECONDS}s)")
            return session_id
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    # Gap too long or no state — start fresh
    session_id = f"voice-{now}"
    print(f"[Session] New session: {session_id}")
    return session_id


def update_session_state(session_id):
    """Update last_active timestamp for the current session."""
    state = {"session_id": session_id, "last_active": int(time.time())}
    with open(SESSION_STATE_FILE, "w") as f:
        json.dump(state, f)



def send_to_openclaw(text):
    """Send user message to OpenClaw agent and get response."""
    print(f"[OpenClaw] Sending: {text}")
    voice_msg = VOICE_CTX_PREFIX + text
    session_id = get_voice_session_id()
    update_session_state(session_id)
    
    reply = _call_openclaw_agent(session_id, voice_msg)
    
    # If request was aborted, retry with same session (transient error)
    if reply == "__ABORTED__":
        print(f"[OpenClaw] Aborted, retrying same session...")
        time.sleep(2)  # brief pause before retry
        reply = _call_openclaw_agent(session_id, voice_msg)
        if reply == "__ABORTED__":
            print(f"[OpenClaw] Retry also aborted")
            return "请求被中断了，稍等一下再试。"
    
    # If got an API error, force new session and retry once
    if reply and reply != "__ABORTED__" and _is_api_error(reply):
        print(f"[OpenClaw] API error detected, forcing new session and retrying...")
        session_id = f"voice-{int(time.time())}"
        update_session_state(session_id)
        reply = _call_openclaw_agent(session_id, voice_msg)
        if reply and _is_api_error(reply):
            print(f"[OpenClaw] Retry also failed with API error")
            return "抱歉，服务暂时出错了，请稍后再试。"
    
    return reply


def _is_api_error(text):
    """Check if the reply is actually an API error message."""
    error_patterns = [
        "HTTP 4", "HTTP 5",
        "Invalid request",
        "invalid_grant",
        "rate_limit",
        "overloaded",
        "internal_error",
        "server_error",
        "Request was aborted",
        "aborted",
    ]
    return any(p in text for p in error_patterns)


def _call_openclaw_agent(session_id, voice_msg):
    """Call openclaw agent and return filtered reply.
    Returns: str (reply), None (empty/timeout), or "__ABORTED__" (request aborted).
    """
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--session-id", session_id, "-m", voice_msg, "--timeout", "600", "--thinking", "off"],
            capture_output=True, text=True, timeout=610
        )
        # Only use stdout (stderr has plugin logs)
        reply = result.stdout.strip()
        stderr = result.stderr.strip() if result.stderr else ""
        if not reply:
            # Check if aborted (stderr or exit code)
            if "aborted" in stderr.lower() or "aborted" in (result.stdout or "").lower():
                print(f"[OpenClaw] Request was aborted")
                return "__ABORTED__"
            print(f"[OpenClaw] No reply in stdout")
            return None
        # Filter out noise lines but preserve [output] marker
        lines = reply.split("\n")
        clean_lines = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            # Preserve lines starting with [output] — that's our TTS marker
            if s.startswith("[output]"):
                clean_lines.append(s)
                continue
            # Skip plugin/debug/internal lines (e.g. [agents/tool-images] ...)
            if re.match(r'^\[[^\]]+\]\s', s):
                continue
            clean_lines.append(s)
        reply = "\n".join(clean_lines).strip()
        if reply:
            return reply
        print(f"[OpenClaw] No reply after filtering")
        return None
    except subprocess.TimeoutExpired:
        print("[OpenClaw] Timeout waiting for response")
        return None
    except Exception as e:
        print(f"[OpenClaw Error] {e}")
        return None


class VoiceAssistant:
    def __init__(self):
        print("[Init] Loading models...")
        self.vad = create_vad()
        self.asr = create_asr()
        self.is_speaking = False  # True when TTS is playing
        self._audio_queue = queue.Queue(maxsize=200)  # ~20s buffer at 100ms chunks
        self._stop_reader = False
        # Start background arecord reader thread (replaces sherpa_onnx.Alsa which
        # intermittently returns stale/fixed data after TTS playback)
        self._arecord_proc = None
        self._reader_thread = threading.Thread(target=self._arecord_reader_loop, daemon=True)
        self._reader_thread.start()
        # Speaker identification (optional)
        self.speaker_id = None
        self._last_passive_track_time = 0  # throttle passive unknown tracking
        if _SPEAKER_ID_AVAILABLE:
            speaker_model = os.path.join(MODELS_DIR, "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")
            if os.path.exists(speaker_model):
                try:
                    self.speaker_id = SpeakerIdentifier(model_path=speaker_model)
                    speakers = self.speaker_id.list_speakers()
                    print(f"[Init] Speaker ID loaded. Enrolled: {speakers if speakers else 'none'}")
                except Exception as e:
                    print(f"[Init] Speaker ID failed to load: {e}")
                    self.speaker_id = None
            else:
                print("[Init] Speaker ID model not found, skipping.")
        # Speaker diarization (optional)
        self.diarizer = None
        if _DIARIZATION_AVAILABLE:
            try:
                self.diarizer = SpeakerDiarizer()
                print(f"[Init] Speaker diarization loaded.")
            except Exception as e:
                print(f"[Init] Speaker diarization failed to load: {e}")
                self.diarizer = None
        # Pre-generate wake response audio for instant playback
        self.wake_wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake_response.wav")
        self._prepare_wake_audio()
        print("[Init] Ready! Listening for wake word '五五零'...")

    def _arecord_reader_loop(self):
        """Background thread: continuously read PCM from arecord subprocess.
        
        Uses arecord instead of sherpa_onnx.Alsa because the latter intermittently
        returns stale/fixed-value data after TTS playback on this hardware.
        arecord has been verified to always return fresh, correct data.
        """
        samples_per_read = int(SAMPLE_RATE * 0.1)  # 100ms chunks
        bytes_per_read = samples_per_read * 2  # 16-bit = 2 bytes per sample
        
        while not self._stop_reader:
            try:
                # Start arecord process: signed 16-bit little-endian, 16kHz, mono, raw PCM
                self._arecord_proc = subprocess.Popen(
                    ["arecord", "-D", ALSA_DEVICE, "-f", "S16_LE", "-r", str(SAMPLE_RATE),
                     "-c", "1", "-t", "raw", "--buffer-size", "16000"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                print("[Reader] arecord started")
                
                while not self._stop_reader:
                    raw = self._arecord_proc.stdout.read(bytes_per_read)
                    if not raw or len(raw) == 0:
                        break  # arecord died, will restart
                    
                    # Convert S16_LE to float32 [-1, 1]
                    int_samples = np.frombuffer(raw, dtype=np.int16)
                    float_samples = int_samples.astype(np.float32) / 32768.0
                    
                    if self.is_speaking:
                        # Discard audio while TTS is playing (avoid self-trigger)
                        continue
                    
                    try:
                        self._audio_queue.put_nowait(float_samples)
                    except queue.Full:
                        # Drop oldest chunk to keep queue fresh
                        try:
                            self._audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._audio_queue.put_nowait(float_samples)
                        
            except Exception as e:
                print(f"[Reader] Error: {e}")
            finally:
                if self._arecord_proc:
                    self._arecord_proc.kill()
                    self._arecord_proc.wait()
                    self._arecord_proc = None
            
            if not self._stop_reader:
                print("[Reader] arecord died, restarting...")
                # Wait until playback finishes before restarting arecord
                # to avoid ALSA device contention (capture gets corrupted
                # if arecord starts while aplay is still using the device)
                while self.is_speaking and not self._stop_reader:
                    time.sleep(0.1)
                time.sleep(0.3)  # small grace period after playback ends

    def _pause_arecord(self):
        """Kill arecord process before playback to release ALSA device.
        The reader thread will auto-restart it after playback ends."""
        if self._arecord_proc:
            try:
                self._arecord_proc.kill()
                self._arecord_proc.wait(timeout=2)
            except Exception:
                pass
            self._arecord_proc = None

    def _drain_queue(self):
        """Discard all queued audio (e.g. after TTS playback)."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _prepare_wake_audio(self):
        """Pre-generate '在呢' audio for fast wake response."""
        # If cached file already exists, skip generation
        if os.path.exists(self.wake_wav):
            print("[Init] Wake response audio found (cached).")
            return
        try:
            mp3_path = self.wake_wav.replace(".wav", ".mp3")
            subprocess.run(
                ["edge-tts", "--voice", TTS_VOICE, "--text", "在呢", "--write-media", mp3_path],
                capture_output=True, timeout=30
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_path, "-ar", "48000", "-ac", "1", "-f", "wav", self.wake_wav],
                capture_output=True, timeout=15
            )
            os.unlink(mp3_path)
            print("[Init] Wake response audio ready.")
        except Exception as e:
            print(f"[Init] Failed to prepare wake audio: {e}")
            self.wake_wav = None

    def _speak_wake(self):
        """Play pre-generated wake response + ding instantly."""
        wake_ding = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake_ding.wav")
        audio_file = wake_ding if os.path.exists(wake_ding) else self.wake_wav
        if audio_file and os.path.exists(audio_file):
            print(f"[TTS] Wake sound ({os.path.basename(audio_file)})")
            self.is_speaking = True
            self._pause_arecord()
            try:
                subprocess.run(["aplay", "-D", ALSA_DEVICE, audio_file],
                               capture_output=True, timeout=10)
            except Exception as e:
                print(f"[TTS Error] {e}")
            finally:
                self.is_speaking = False
                self._drain_queue()
        else:
            self.is_speaking = True
            self._pause_arecord()
            speak("在呢")
            self.is_speaking = False
            self._drain_queue()

    def listen_loop(self):
        """Main loop: listen for wake word, then process commands."""
        chunk_count = 0
        max_amp = 0.0
        recent_max = 0.0

        while True:
            try:
                # Read audio chunk from background reader queue
                try:
                    samples = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                chunk_count += 1
                arr = np.array(samples, dtype=np.float32)
                cur_max = float(np.max(np.abs(arr))) if len(arr) > 0 else 0.0
                if cur_max > max_amp:
                    max_amp = cur_max
                if cur_max > recent_max:
                    recent_max = cur_max
                if chunk_count % 100 == 0:
                    print(f"[Debug] chunks={chunk_count}, max_amp={max_amp:.4f}, recent_max={recent_max:.4f}, is_speech={self.vad.is_speech_detected()}")
                    recent_max = 0.0  # reset per-window max

                # Feed to VAD
                self.vad.accept_waveform(arr)

                # Check if VAD detected speech
                if self.vad.empty():
                    continue

                print(f"[Debug] VAD has segment! empty={self.vad.empty()}")

                while not self.vad.empty():
                    try:
                        speech_segment = self.vad.front
                        # Copy samples BEFORE pop — pop may free underlying memory
                        audio = np.array(speech_segment.samples, dtype=np.float32).copy()
                        self.vad.pop()
                        dur = len(audio) / SAMPLE_RATE
                        max_abs = float(np.max(np.abs(audio)))
                        print(f"[Debug] segment duration={dur:.2f}s, max_abs={max_abs:.4f}")
                        if len(audio) < SAMPLE_RATE * 0.3:
                            print(f"[Debug] Too short ({dur:.2f}s), skipping")
                            continue
                        if max_abs < 0.01:
                            print(f"[Debug] Too quiet (max_abs={max_abs:.4f}), skipping")
                            continue
                        text = recognize(self.asr, audio)
                        print(f"[Debug] ASR result: '{text}'")
                        if not text:
                            continue

                        print(f"[Heard] {text}")

                        # Passive unknown speaker tracking for non-wake speech
                        if (not is_wake_word(text) and self.speaker_id
                                and self.speaker_id.list_speakers()
                                and len(audio) >= SAMPLE_RATE * 1.0):
                            try:
                                name, score = self.speaker_id.identify(audio)
                                if name == "unknown":
                                    result = self.speaker_id.track_unknown(audio)
                                    if result:
                                        cid = result["cluster_id"]
                                        count = result["count"]
                                        print(f"[SpeakerID] Passive track: unknown cluster '{cid}' "
                                              f"(count={count}, score={score:.3f})")
                                        if result["should_notify"]:
                                            self._notify_unknown_speaker(cid, count)
                            except Exception as e:
                                print(f"[SpeakerID] Passive track error: {e}")

                        # Check for wake word
                        if is_wake_word(text):
                            print("[Wake] Detected!")
                            # Speaker-gated wake: if speakers are enrolled,
                            # only enrolled speakers can trigger wake
                            wake_speaker = None
                            if self.speaker_id and self.speaker_id.list_speakers():
                                name, score = self.speaker_id.identify(audio)
                                if name == "unknown":
                                    print(f"[Wake] Rejected: unregistered speaker (best_score={score:.3f})")
                                    # Track unknown speaker for gradual learning
                                    try:
                                        result = self.speaker_id.track_unknown(audio)
                                        if result and result["should_notify"]:
                                            cid = result["cluster_id"]
                                            count = result["count"]
                                            print(f"[SpeakerID] Unknown cluster '{cid}' reached {count} occurrences, notifying user")
                                            self._notify_unknown_speaker(cid, count)
                                    except Exception as e:
                                        print(f"[SpeakerID] track_unknown error: {e}")
                                    continue
                                print(f"[Wake] Accepted: {name} (score={score:.3f})")
                                wake_speaker = name
                            else:
                                print("[Wake] No enrolled speakers, allowing anyone")
                            self._speak_wake()
                            self.vad.reset()
                            self.listen_for_command(wake_speaker=wake_speaker)
                    except Exception as e:
                        print(f"[Error in VAD loop] {e}")
                        break

            except KeyboardInterrupt:
                print("\n[Exit] Bye!")
                break
            except Exception as e:
                print(f"[Error] {e}")
                time.sleep(0.5)

    def listen_for_command(self, wake_speaker=None):
        """After wake word, collect full command audio.
        
        Args:
            wake_speaker: name of the speaker who triggered wake (if identified)
        """
        print("[Listen] Waiting for command...")

        # Drain stale audio from queue (wake sound playback residue already drained in _speak_wake)
        self._drain_queue()
        self.vad.reset()

        # Give user a brief moment to start speaking after ding
        time.sleep(0.3)

        start_time = time.time()
        all_audio = []
        speech_started = False
        silence_start = None

        while time.time() - start_time < WAKE_LISTEN_TIMEOUT:
            try:
                samples = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                if speech_started and silence_start is None:
                    silence_start = time.time()
                if silence_start and time.time() - silence_start >= POST_SPEECH_SILENCE:
                    print("[Listen] End of speech detected (queue empty).")
                    break
                continue

            if len(samples) == 0:
                continue

            arr = np.array(samples, dtype=np.float32)
            all_audio.append(arr)
            self.vad.accept_waveform(arr)

            # Use audio energy to detect speech activity
            energy = float(np.max(np.abs(arr)))
            has_energy = energy > 0.1

            if has_energy:
                speech_started = True
                silence_start = None
            elif speech_started:
                # Speech ended, start counting silence
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= POST_SPEECH_SILENCE:
                    print("[Listen] End of speech detected.")
                    break

        if not speech_started:
            print("[Listen] Timeout, no command heard.")
            return

        # Collect all VAD segments for recognition
        collected = []
        while not self.vad.empty():
            seg = self.vad.front
            # Copy samples BEFORE pop — pop may free underlying memory
            seg_audio = np.array(seg.samples, dtype=np.float32).copy()
            self.vad.pop()
            if len(seg_audio) >= SAMPLE_RATE * 0.3:
                collected.append(seg_audio)

        if not collected:
            print("[Listen] No valid speech segments.")
            return

        # Play dong sound to signal "recording stopped, processing"
        dong_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dong.wav")
        if os.path.exists(dong_path):
            self.is_speaking = True
            self._pause_arecord()
            try:
                subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, dong_path],
                               capture_output=True, timeout=3)
            except Exception as e:
                print(f"[Listen] Dong playback failed: {e}")
            finally:
                self.is_speaking = False
                self._drain_queue()

        audio = np.concatenate(collected)
        duration = len(audio) / SAMPLE_RATE
        print(f"[Listen] Collected {duration:.2f}s of speech")

        # Speaker identification per VAD segment + ASR
        # For short commands (<10s), VAD segments + per-segment speaker ID is
        # more reliable than offline diarization (which needs long audio).
        # For long audio (>=10s), use diarization for better clustering.
        if duration >= 10.0 and self.diarizer:
            # Long audio: use diarization
            try:
                print("[Listen] Running speaker diarization (long audio)...")
                segments = self.diarizer.process_and_extract(
                    audio, speaker_identifier=self.speaker_id
                )
                if segments:
                    diar_text = segments_to_text(segments, audio, self.asr)
                    if diar_text:
                        print(f"[Command/Diarized]\n{diar_text}")
                        self.handle_command(diar_text, audio=audio, diarized=True, wake_speaker=wake_speaker)
                        return
                print("[Listen] Diarization produced no usable result, falling back")
            except Exception as e:
                print(f"[Listen] Diarization failed: {e}, falling back")

        # Short audio or diarization fallback: per-segment speaker ID + ASR
        if self.speaker_id and len(collected) > 0:
            lines = []
            for i, seg_audio in enumerate(collected):
                # ASR this segment
                text = recognize(self.asr, seg_audio)
                if not text:
                    continue
                # Speaker ID on this segment (need >= 0.5s for embedding)
                if len(seg_audio) >= SAMPLE_RATE * 0.5:
                    try:
                        name, score = self.speaker_id.identify(seg_audio)
                        if name != "unknown":
                            speaker = name
                        else:
                            speaker = "未知说话人"
                        print(f"[Listen] Seg {i}: {speaker} (score={score:.3f}) -> {text}")
                        lines.append(f"{speaker}(confidence={score:.2f}): {text}")
                    except Exception as e:
                        print(f"[Listen] Seg {i} speaker ID error: {e}")
                        speaker = wake_speaker or "未知说话人"
                        lines.append(f"{speaker}: {text}")
                else:
                    # Too short for speaker ID, assume wake speaker
                    speaker = wake_speaker or "未知说话人"
                    print(f"[Listen] Seg {i}: too short for ID, assuming {speaker} -> {text}")
                    lines.append(f"{speaker}: {text}")

            if lines:
                full_text = "\n".join(lines)
                print(f"[Command/PerSeg]\n{full_text}")
                self.handle_command(full_text, audio=audio, diarized=True, wake_speaker=wake_speaker)
                return

        # Final fallback: plain ASR on full audio
        print(f"[Listen] Recognizing full audio...")
        text = recognize(self.asr, audio)
        if text:
            print(f"[Command] {text}")
            self.handle_command(text, audio, wake_speaker=wake_speaker)
        else:
            print("[Listen] ASR returned empty.")

    def handle_command(self, text, audio=None, diarized=False, wake_speaker=None):
        """Process a voice command.
        
        Args:
            text: recognized text, or diarized multi-speaker text ("speaker: text" per line)
            audio: original audio (for speaker identification and embedding update)
            diarized: if True, text is already in "speaker: text" format from diarization
            wake_speaker: name of the speaker who triggered wake (for embedding update)
        """
        print(f"[Process] {text}")

        if diarized:
            # Already formatted as "speaker: text" lines from diarization
            full_text = text
        else:
            # Single-speaker fallback: try speaker identification
            speaker_prefix = ""
            if self.speaker_id and audio is not None:
                try:
                    name, score = self.speaker_id.identify(audio)
                    if name != "unknown":
                        speaker_prefix = f"{name}: "
                        print(f"[SpeakerID] Identified: {name} (score={score:.3f})")
                    else:
                        speaker_prefix = "未知说话人: "
                        print(f"[SpeakerID] Unknown speaker (best score={score:.3f})")
                except Exception as e:
                    print(f"[SpeakerID] Error: {e}")
            full_text = f"{speaker_prefix}{text}" if speaker_prefix else text

        # Send to OpenClaw
        self.is_speaking = True
        self._pause_arecord()
        response = send_to_openclaw(full_text)

        # Speak response (arecord stays paused throughout)
        if response:
            speak(response)
        else:
            speak("没拿到回复，可能网络有点问题，再试一次？")

        # Incremental voiceprint update: use the command audio to refine
        # the enrolled speaker's embedding (越用越准)
        if wake_speaker and audio is not None and self.speaker_id:
            try:
                updated = self.speaker_id.update_embedding(wake_speaker, audio)
                if updated:
                    print(f"[SpeakerID] Voiceprint updated for {wake_speaker}")
            except Exception as e:
                print(f"[SpeakerID] Voiceprint update error: {e}")

        # Track unknown speakers from diarization results too
        if not wake_speaker and audio is not None and self.speaker_id:
            try:
                result = self.speaker_id.track_unknown(audio)
                if result and result["should_notify"]:
                    self._notify_unknown_speaker(result["cluster_id"], result["count"])
            except Exception as e:
                print(f"[SpeakerID] track_unknown in command error: {e}")

        # Resume listening
        self.is_speaking = False
        self._drain_queue()

    def _notify_unknown_speaker(self, cluster_id, count):
        """Notify user (via OpenClaw) about a frequently seen unknown speaker."""
        try:
            msg = (f"系统消息：有一个未注册的说话人已经累计被识别到 {count} 次"
                   f"（ID: {cluster_id}）。"
                   f"请问是否需要给这个人注册名字？"
                   f"可以通过语音告诉我这个人的名字，或者说\"忽略\"跳过。")
            response = send_to_openclaw(msg)
            if response:
                speak(response)
        except Exception as e:
            print(f"[SpeakerID] Notify error: {e}")


def play_startup_sound():
    """Play a startup chime to indicate voice assistant is ready."""
    ding_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ding.wav")
    if os.path.exists(ding_path):
        try:
            # Play twice for a distinct startup sound
            subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, ding_path],
                           capture_output=True, timeout=3)
            time.sleep(0.1)
            subprocess.run(["aplay", "-D", PLAYBACK_DEVICE, ding_path],
                           capture_output=True, timeout=3)
            print("[Init] Startup sound played.")
        except Exception as e:
            print(f"[Init] Startup sound failed: {e}")


def main():
    # Check models exist
    vad_model = os.path.join(MODELS_DIR, "silero_vad.onnx")
    sv_dir = os.path.join(MODELS_DIR, "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")

    if not os.path.exists(vad_model):
        print(f"[Error] VAD model not found: {vad_model}")
        sys.exit(1)
    if not os.path.exists(sv_dir):
        print(f"[Error] SenseVoice model not found: {sv_dir}")
        sys.exit(1)

    assistant = VoiceAssistant()
    assistant.is_speaking = True
    assistant._pause_arecord()
    play_startup_sound()
    time.sleep(0.5)  # ensure ALSA device is fully released after playback
    assistant.is_speaking = False
    assistant._drain_queue()
    assistant.listen_loop()


if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            print("\n[Exit] Stopped by user.")
            break
        except Exception as e:
            print(f"[Crash] {e}, restarting in 3s...")
            time.sleep(3)
