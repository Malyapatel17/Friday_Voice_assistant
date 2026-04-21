"""
friday/audio.py — Microphone stream, wake word, command & chat detection

NOTE: vosk-model-en-us-0.22 does NOT support runtime grammar graphs.
      All three recognizers use free-form transcription; keywords are
      matched in plain Python after the fact.
"""

import json

import pyaudio
from vosk import KaldiRecognizer, Model


class AudioManager:
    """Owns the PyAudio stream and all Vosk recognizers."""

    SAMPLE_RATE  = 16000
    FRAME_LENGTH = 4000   # 250 ms chunks

    def __init__(self, model_path, wake_word):
        self.wake_word = wake_word.lower()

        print(f"📂 Loading speech model from '{model_path}'...")
        model = Model(model_path=model_path)

        # All three recognizers use FREE-FORM transcription (no grammar arg)
        # because vosk-model-en-us-0.22 doesn't support runtime graphs.
        self.wake_recognizer    = KaldiRecognizer(model, self.SAMPLE_RATE)
        self.command_recognizer = KaldiRecognizer(model, self.SAMPLE_RATE)
        self.chat_recognizer    = KaldiRecognizer(model, self.SAMPLE_RATE)

        self.pa     = pyaudio.PyAudio()
        self.stream = None

    # ── Stream ────────────────────────────────────────────────────────────────

    def start_stream(self):
        self.stream = self.pa.open(
            rate=self.SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.FRAME_LENGTH
        )

    def read_frame(self):
        return self.stream.read(self.FRAME_LENGTH, exception_on_overflow=False)

    # ── Wake word ─────────────────────────────────────────────────────────────

    def detect_wake_word(self, audio_bytes):
        """Return True when the wake word is heard."""
        if self.wake_recognizer.AcceptWaveform(audio_bytes):
            text = json.loads(self.wake_recognizer.Result()).get("text", "").lower()
            if text:
                print(f"[wake] heard: '{text}'")
            return self.wake_word in text
        # Also check partial results so there's no 1-second lag
        partial = json.loads(self.wake_recognizer.PartialResult()).get("partial", "").lower()
        return self.wake_word in partial

    # ── Command ───────────────────────────────────────────────────────────────

    def detect_command(self, audio_bytes):
        """Returns 'work' | 'home' | 'chat' | 'close_tabs' | 'rest' | 'stop' | None"""
        if self.command_recognizer.AcceptWaveform(audio_bytes):
            text = json.loads(self.command_recognizer.Result()).get("text", "").lower()
            if text:
                print(f"[command] heard: '{text}'")
                return self._parse_command(text)

        # Check partials too so commands feel snappy
        partial = json.loads(self.command_recognizer.PartialResult()).get("partial", "").lower()
        if partial:
            return self._parse_command(partial)

        return None

    def _parse_command(self, text):
        if not text:
            return None
        if ("start" in text and "work" in text) or "start work" in text:
            return "work"
        if "daddy" in text or ("home" in text and "start" not in text):
            return "home"
        if "chat" in text or ("let" in text and "talk" in text):
            return "chat"
        if "close" in text and ("tab" in text or "browser" in text):
            return "close_tabs"
        if "rest" in text or "you can rest" in text or "take a rest" in text:
            return "rest"
        if any(w in text for w in ["goodbye", "stop", "exit", "bye"]):
            return "stop"
        return None

    # ── Chat transcription ────────────────────────────────────────────────────

    def detect_chat_speech(self, audio_bytes):
        """Returns transcribed text string or None."""
        if self.chat_recognizer.AcceptWaveform(audio_bytes):
            text = json.loads(self.chat_recognizer.Result()).get("text", "").strip()
            if text and text != "[unk]":
                return text
        return None

    # ── Flush / cleanup ───────────────────────────────────────────────────────

    def flush(self):
        """Reset all recognizer buffers — call on every state transition."""
        self.wake_recognizer.FinalResult()
        self.command_recognizer.FinalResult()
        self.chat_recognizer.FinalResult()

    def cleanup(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.pa:
            self.pa.terminate()