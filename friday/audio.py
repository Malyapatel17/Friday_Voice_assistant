"""
friday/audio.py — Microphone stream, wake word & command detection

Wake word : Vosk small model  — streaming, CPU, loads in ~0.5 s
Commands  : faster-whisper tiny.en on CUDA — <200 ms per utterance on RTX 3050Ti

Why two models?
  Vosk streams 32 ms frames continuously with near-zero CPU.
  faster-whisper is far more accurate for full sentences but processes
  a recorded clip, not a live stream — perfect for the command phase.
"""

import json
import sys

import numpy as np
import pyaudio
from vosk import KaldiRecognizer, Model


class AudioManager:
    SAMPLE_RATE = 16000
    WAKE_CHUNK  = 512    # 32 ms  — tiny, keeps Vosk latency minimal
    CMD_CHUNK   = 1600   # 100 ms — used while recording a command

    # ── Init ──────────────────────────────────────────────────────────────────

    def __init__(self, model_path: str, wake_word: str):
        self.wake_word = wake_word.lower()
        self.stream    = None

        # PyAudio handle — created once, never recreated
        self._pa = pyaudio.PyAudio()

        # ── Vosk small (wake word only) ────────────────────────────────────
        print(f"📂 Loading wake-word model from '{model_path}' ...")
        try:
            vosk_model = Model(model_path=model_path)
        except Exception as exc:
            print(f"❌ Could not load Vosk model: {exc}")
            print("   Download vosk-model-small-en-us-0.15 from")
            print("   https://alphacephei.com/vosk/models and extract it")
            print(f"   to the folder '{model_path}' next to main.py")
            sys.exit(1)

        self._wake_rec = KaldiRecognizer(vosk_model, self.SAMPLE_RATE)
        print("✅ Wake-word model ready")

        # ── faster-whisper tiny.en (commands) ─────────────────────────────
        print("📂 Loading command model (faster-whisper tiny.en) ...")
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                "tiny.en",
                device="cuda",
                compute_type="float16",   # half-precision — 2× faster on RTX
            )
            print("✅ Command model on GPU (CUDA float16)")
        except Exception as exc:
            print(f"⚠️  CUDA init failed ({exc}) — falling back to CPU int8")
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                "tiny.en",
                device="cpu",
                compute_type="int8",
            )
            print("✅ Command model on CPU (int8)")

    # ── Microphone stream ─────────────────────────────────────────────────────

    def start_stream(self):
        """Open the microphone stream. Crashes early with a clear message if mic is missing."""
        try:
            self.stream = self._pa.open(
                rate=self.SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.WAKE_CHUNK,
            )
        except OSError as exc:
            print(f"❌ Cannot open microphone: {exc}")
            print("   Make sure a microphone is connected and not in use by another app.")
            sys.exit(1)

    def read_frame(self) -> bytes:
        """Read one WAKE_CHUNK frame — call this in the standby loop."""
        return self.stream.read(self.WAKE_CHUNK, exception_on_overflow=False)

    # ── Wake word detection (streaming, Vosk) ─────────────────────────────────

    def detect_wake_word(self, audio_bytes: bytes) -> bool:
        """Return True the moment the wake word appears in Vosk output."""
        if self._wake_rec.AcceptWaveform(audio_bytes):
            text = json.loads(self._wake_rec.Result()).get("text", "").lower()
            if text:
                print(f"[wake] '{text}'")
            return self.wake_word in text

        # Partial results give sub-second reaction time
        partial = json.loads(self._wake_rec.PartialResult()).get("partial", "").lower()
        return self.wake_word in partial

    # ── Command recording ─────────────────────────────────────────────────────

    def record_command(
        self,
        max_seconds: float = 6.0,
        silence_threshold: int = 450,
        silence_secs: float = 1.0,
    ) -> np.ndarray:
        """
        Record audio from the mic until silence or max_seconds, whichever comes first.

        silence_threshold : mean absolute amplitude (0–32 768) below which = silent
        silence_secs      : how long silence must last before we stop

        Returns a float32 numpy array normalised to [-1, 1].
        """
        frames: list[bytes] = []
        silent_count = 0
        silent_limit = max(1, int(self.SAMPLE_RATE * silence_secs   / self.CMD_CHUNK))
        max_count    =       int(self.SAMPLE_RATE * max_seconds     / self.CMD_CHUNK)
        # Don't start silence-checking until at least 300 ms of audio is captured
        min_voice    =       int(self.SAMPLE_RATE * 0.3             / self.CMD_CHUNK)

        for i in range(max_count):
            data = self.stream.read(self.CMD_CHUNK, exception_on_overflow=False)
            frames.append(data)

            amplitude = np.abs(np.frombuffer(data, dtype=np.int16)).mean()

            if i >= min_voice:
                if amplitude < silence_threshold:
                    silent_count += 1
                    if silent_count >= silent_limit:
                        break
                else:
                    silent_count = 0

        raw = b"".join(frames)
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32_768.0

    # ── Command transcription (faster-whisper) ────────────────────────────────

    def transcribe_command(self, audio_np: np.ndarray) -> str:
        """Transcribe a recorded audio clip and return the cleaned text."""
        segments, _ = self._whisper.transcribe(
            audio_np,
            language="en",
            beam_size=1,          # greedy — fastest, fine for short commands
            vad_filter=True,      # skip leading/trailing silence automatically
            vad_parameters={"min_silence_duration_ms": 400},
        )
        text = " ".join(s.text for s in segments).strip().lower()
        if text:
            print(f"[cmd ] '{text}'")
        return text

    # ── Command parser ────────────────────────────────────────────────────────

    @staticmethod
    def parse_command(text: str) -> str | None:
        """Map a transcribed sentence to an internal command token."""
        if not text:
            return None
        t = text.lower()

        if ("start" in t and "work" in t) or "start work" in t:
            return "work"

        if "daddy" in t or ("home" in t and "start" not in t):
            return "home"

        if "close" in t and ("tab" in t or "browser" in t or "all" in t):
            return "close_tabs"

        if any(w in t for w in ["rest", "sleep", "goodbye", "bye", "stop", "exit"]):
            return "rest"

        return None

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def flush(self):
        """Reset Vosk buffer on every state transition to avoid stale audio."""
        self._wake_rec.FinalResult()

    def cleanup(self):
        """Gracefully close stream and PortAudio. Safe to call multiple times."""
        try:
            if self.stream and not self.stream.is_stopped():
                self.stream.stop_stream()
            if self.stream:
                self.stream.close()
        except Exception:
            pass
        try:
            self._pa.terminate()
        except Exception:
            pass
