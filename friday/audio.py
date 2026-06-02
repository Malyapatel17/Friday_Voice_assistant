"""
friday/audio.py -- Microphone stream, wake word & command detection

Wake word : Vosk small model  -- streaming, CPU, loads in ~0.5 s
Commands  : faster-whisper tiny.en on CUDA -- <200 ms per utterance on RTX 3050Ti

Fixes in this version:
  - transcribe_command wraps generator consumption in try/except
    (unhandled CUDA exceptions inside the generator were crashing the program)
  - WhisperModel loaded once with explicit fallback chain: CUDA -> CPU
  - record_command protected against stream read errors
"""

import json
import sys
import traceback

import numpy as np
import pyaudio
from vosk import KaldiRecognizer, Model


class AudioManager:
    SAMPLE_RATE = 16000
    WAKE_CHUNK  = 512    # 32 ms  -- tiny, keeps Vosk latency minimal
    CMD_CHUNK   = 1600   # 100 ms -- used while recording a command

    # ── Init ──────────────────────────────────────────────────────────────────

    def __init__(self, model_path: str, wake_word: str):
        self.wake_word   = wake_word.lower()
        self.stream      = None
        self._whisper    = None
        self._whisper_ok = False

        # PyAudio handle -- created once, never recreated
        self._pa = pyaudio.PyAudio()

        # ── Vosk small (wake word only) ────────────────────────────────────
        print(f"[INFO] Loading wake-word model from '{model_path}' ...")
        try:
            vosk_model = Model(model_path=model_path)
        except Exception as exc:
            print(f"[ERROR] Could not load Vosk model: {exc}")
            print("  Download vosk-model-small-en-us-0.15 from")
            print("  https://alphacephei.com/vosk/models and extract it")
            print(f"  to the folder '{model_path}' next to main.py")
            sys.exit(1)

        self._wake_rec = KaldiRecognizer(vosk_model, self.SAMPLE_RATE)
        print("[OK] Wake-word model ready")

        # ── faster-whisper tiny.en (commands) ─────────────────────────────
        print("[INFO] Loading command model (faster-whisper tiny.en) ...")
        self._load_whisper()

    def _load_whisper(self):
        """Load faster-whisper with CUDA first, CPU fallback. Sets _whisper_ok flag."""
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                "tiny.en",
                device="cuda",
                compute_type="float16",
            )
            # Force a dummy transcription to confirm CUDA is actually working.
            # The model loads without error but can crash on first real use
            # if the CUDA runtime is misconfigured.
            dummy = np.zeros(16000, dtype=np.float32)
            list(self._whisper.transcribe(dummy, language="en")[0])
            self._whisper_ok = True
            print("[OK] Command model on GPU (CUDA float16)")
            return
        except Exception as exc:
            print(f"[WARN] CUDA failed ({type(exc).__name__}: {exc})")
            print("[INFO] Falling back to CPU int8 ...")

        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                "tiny.en",
                device="cpu",
                compute_type="int8",
            )
            dummy = np.zeros(16000, dtype=np.float32)
            list(self._whisper.transcribe(dummy, language="en")[0])
            self._whisper_ok = True
            print("[OK] Command model on CPU (int8)")
        except Exception as exc:
            print(f"[ERROR] Could not load faster-whisper at all: {exc}")
            traceback.print_exc()
            print("[WARN] Commands will not work. Fix faster-whisper and restart.")
            self._whisper_ok = False

    # ── Microphone stream ─────────────────────────────────────────────────────

    def start_stream(self):
        """Open the microphone stream."""
        try:
            self.stream = self._pa.open(
                rate=self.SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.WAKE_CHUNK,
            )
        except OSError as exc:
            print(f"[ERROR] Cannot open microphone: {exc}")
            print("  Make sure a microphone is connected and not in use by another app.")
            sys.exit(1)

    def read_frame(self) -> bytes:
        """Read one WAKE_CHUNK frame -- call this in the standby loop."""
        return self.stream.read(self.WAKE_CHUNK, exception_on_overflow=False)

    # ── Wake word detection (streaming, Vosk) ─────────────────────────────────

    def detect_wake_word(self, audio_bytes: bytes) -> bool:
        """Return True the moment the wake word appears in Vosk output."""
        if self._wake_rec.AcceptWaveform(audio_bytes):
            text = json.loads(self._wake_rec.Result()).get("text", "").lower()
            if text:
                print(f"[wake] '{text}'")
            return self.wake_word in text

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
        Record audio from the mic until silence or max_seconds.
        Returns a float32 numpy array normalised to [-1, 1].
        """
        frames       = []
        silent_count = 0
        silent_limit = max(1, int(self.SAMPLE_RATE * silence_secs / self.CMD_CHUNK))
        max_count    =       int(self.SAMPLE_RATE * max_seconds   / self.CMD_CHUNK)
        min_voice    =       int(self.SAMPLE_RATE * 0.3           / self.CMD_CHUNK)

        for i in range(max_count):
            try:
                data = self.stream.read(self.CMD_CHUNK, exception_on_overflow=False)
            except Exception as exc:
                print(f"[WARN] Mic read error during command: {exc}")
                break

            frames.append(data)
            amplitude = np.abs(np.frombuffer(data, dtype=np.int16)).mean()

            if i >= min_voice:
                if amplitude < silence_threshold:
                    silent_count += 1
                    if silent_count >= silent_limit:
                        break
                else:
                    silent_count = 0

        if not frames:
            return np.zeros(1600, dtype=np.float32)

        raw = b"".join(frames)
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32_768.0

    # ── Command transcription (faster-whisper) ────────────────────────────────

    def transcribe_command(self, audio_np: np.ndarray) -> str:
        """
        Transcribe a recorded audio clip and return the cleaned text.
        Returns empty string on any failure -- never raises.
        """
        if not self._whisper_ok or self._whisper is None:
            print("[WARN] Whisper not available -- skipping transcription")
            return ""

        try:
            segments_gen, _ = self._whisper.transcribe(
                audio_np,
                language="en",
                beam_size=1,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400},
            )
            # Consume the generator inside try/except.
            # Exceptions from CUDA can surface here (not at .transcribe() call).
            segments = list(segments_gen)
            text = " ".join(s.text for s in segments).strip().lower()
            if text:
                print(f"[cmd ] '{text}'")
            return text

        except Exception as exc:
            print(f"[ERROR] Transcription failed: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            # Try reloading the model on next call
            print("[INFO] Attempting to reload Whisper model ...")
            self._whisper_ok = False
            self._load_whisper()
            return ""

    # ── Command parser ────────────────────────────────────────────────────────

    @staticmethod
    def parse_command(text: str) -> tuple[str | None, str]:
        """Map a transcribed sentence to (token, payload).

        token is one of: "work", "home", "close_tabs", "rest", "ask", None.
        payload is the question text (for "ask") or "" otherwise.
        """
        if not text:
            return None, ""
        t = text.lower().strip()

        # Existing verbs (checked first so the four legacy verbs never get
        # shadowed by the implicit "ask" question-word triggers).
        if ("start" in t and "work" in t) or "start work" in t:
            return "work", ""
        if "daddy" in t or ("home" in t and "start" not in t):
            return "home", ""
        if "close" in t and ("tab" in t or "browser" in t or "all" in t):
            return "close_tabs", ""
        if any(w in t for w in ["rest", "sleep", "goodbye", "bye", "stop", "exit"]):
            return "rest", ""

        # Explicit "ask <question>" trigger.
        if t.startswith("ask "):
            return "ask", t[4:].strip()

        # "question for you" / "got a question" preamble.
        for marker in ("question for you", "got a question"):
            if marker in t:
                payload = t.split(marker, 1)[1].strip(" ,.:?")
                return "ask", payload

        # Implicit ask: utterance starts with a question word.
        first = t.split(" ", 1)[0]
        if first in ("what", "who", "when", "where", "why", "how",
                     "is", "are", "can", "should", "do", "does"):
            return "ask", t

        return None, ""

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