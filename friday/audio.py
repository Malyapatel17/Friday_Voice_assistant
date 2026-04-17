"""
friday/audio.py — Microphone stream, wake word, command & chat detection
"""

import json

import pyaudio
from vosk import KaldiRecognizer, Model


class AudioManager:
    """Owns the PyAudio stream and all Vosk recognizers."""

    SAMPLE_RATE = 16000
    FRAME_LENGTH = 4000  # 250ms chunks

    def __init__(self, model_path, wake_word):
        self.wake_word = wake_word

        # Load Vosk model once — shared across all recognizers
        print(f"📂 Loading speech model from '{model_path}'...")
        model = Model(model_path=model_path)

        # Wake word recognizer (narrow grammar)
        self.wake_recognizer = KaldiRecognizer(
            model, self.SAMPLE_RATE,
            f'["{wake_word}", "[unk]"]'
        )

        # Command recognizer (known command phrases)
        self.command_recognizer = KaldiRecognizer(
            model, self.SAMPLE_RATE,
            '["let\'s start the work", "start the work", "lets start the work", '
            '"daddy is home", "daddy\'s home", '
            '"let\'s chat", "lets chat", "hey chat", '
            '"close all tabs", "close tabs", '
            '"you can rest", "take a rest", "rest now", '
            '"goodbye", "stop", "exit", "bye", "[unk]"]'
        )

        # Chat recognizer — no grammar, free transcription
        self.chat_recognizer = KaldiRecognizer(model, self.SAMPLE_RATE)

        # PyAudio
        self.pa = pyaudio.PyAudio()
        self.stream = None

    # ── Stream ────────────────────────────────────────────────────────────

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

    # ── Wake word ─────────────────────────────────────────────────────────

    def detect_wake_word(self, audio_bytes):
        if self.wake_recognizer.AcceptWaveform(audio_bytes):
            result = json.loads(self.wake_recognizer.Result())
            text = result.get("text", "").lower()
            return self.wake_word in text
        return False

    # ── Command ───────────────────────────────────────────────────────────

    def detect_command(self, audio_bytes):
        """Returns 'work' | 'home' | 'chat' | 'stop' | None"""
        if self.command_recognizer.AcceptWaveform(audio_bytes):
            result = json.loads(self.command_recognizer.Result())
            text = result.get("text", "").lower()
            if text:
                if "start" in text and "work" in text:
                    return "work"
                if "daddy" in text or ("home" in text and "start" not in text):
                    return "home"
                if "chat" in text or "talk" in text:
                    return "chat"
                if "close" in text and ("tab" in text or "tabs" in text):
                    return "close_tabs"
                if "rest" in text:
                    return "rest"
                if any(w in text for w in ["goodbye", "stop", "exit", "bye"]):
                    return "stop"
        return None

    # ── Chat transcription ────────────────────────────────────────────────

    def detect_chat_speech(self, audio_bytes):
        """Returns transcribed text string or None."""
        if self.chat_recognizer.AcceptWaveform(audio_bytes):
            result = json.loads(self.chat_recognizer.Result())
            text = result.get("text", "").strip()
            if text and text != "[unk]":
                return text
        return None

    # ── Flush / cleanup ───────────────────────────────────────────────────

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
