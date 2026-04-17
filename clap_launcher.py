#!/usr/bin/env python3
"""
Friday - Voice-Activated App Launcher
Say 'Friday' to activate, then give a voice command to launch apps.

Commands:
  "Let's start the work" → Opens Claude.ai, ChatGPT, VS Code
  "Daddy is home"        → Opens YouTube, Hotstar, Amazon Prime

GitHub: https://github.com/tpateeq/wake-up
"""

import pyaudio
import subprocess
import time
import sys
import platform
import signal

try:
    from vosk import Model, KaldiRecognizer
    import json
except ImportError:
    print("❌ Vosk not installed!")
    print("\nInstall it with:")
    print("  pip install vosk")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("❌ pyttsx3 not installed!")
    print("\nInstall it with:")
    print("  pip install pyttsx3")
    sys.exit(1)


class FridayLauncher:
    """Friday voice assistant — wake word + voice command launcher"""

    def __init__(self, wake_word="friday", debug=False, model_path="model"):
        self.wake_word = wake_word.lower()
        self.debug = debug
        self.model_path = model_path

        # Detect operating system
        self.os_type = platform.system()
        print(f"🖥️  Detected OS: {self.os_type}")

        # State management
        self.is_active = False
        self.activation_time = 0
        self.active_duration = 10  # seconds to wait for voice command
        self.running = True

        # Find female voice ID for TTS
        self.tts_voice_id = None
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'zira' in voice.name.lower() or 'female' in voice.name.lower():
                    self.tts_voice_id = voice.id
                    break
            if not self.tts_voice_id and voices:
                self.tts_voice_id = voices[0].id
            engine.stop()
            print("✅ Friday voice ready!")
        except Exception as e:
            print(f"⚠️  TTS init warning: {e} — continuing without voice")

        # Initialize Vosk models
        try:
            model = Model(model_path=self.model_path)
            # Wake word recognizer
            self.wake_recognizer = KaldiRecognizer(
                model, 16000, f'["{self.wake_word}", "[unk]"]'
            )
            # Command recognizer — includes variants for better recognition
            self.command_recognizer = KaldiRecognizer(
                model, 16000,
                '["let\'s start the work", "start the work", "lets start the work", '
                '"daddy is home", "daddy\'s home", "[unk]"]'
            )
            print(f"✅ Wake word '{self.wake_word}' loaded successfully!")
            print("💡 This runs 100% locally - no internet needed!\n")
        except Exception as e:
            print(f"❌ Error initializing Vosk: {e}")
            print("\nMake sure you have:")
            print("  1. Installed vosk: pip install vosk")
            print("  2. Downloaded a model from https://alphacephei.com/vosk/models")
            print(f"  3. Extracted to '{self.model_path}' folder in this directory")
            sys.exit(1)

        # Audio setup — Vosk uses 16kHz
        self.sample_rate = 16000
        self.frame_length = 4000  # 250ms chunks at 16kHz

        # PyAudio
        self.pa = pyaudio.PyAudio()
        self.audio_stream = None

        # Setup signal handler for clean exit
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n👋 Shutting down Friday...")
        self.running = False

    def speak(self, text):
        """Speak text using TTS — fresh engine each call to avoid pyttsx3 state bugs"""
        print(f"🗣️  Friday: {text}")
        if not self.tts_voice_id:
            return
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
            engine = pyttsx3.init()
            engine.setProperty('voice', self.tts_voice_id)
            engine.setProperty('rate', 180)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"⚠️  TTS error: {e}")
        finally:
            if self.audio_stream:
                self.audio_stream.start_stream()

    def start_audio_stream(self):
        """Start the audio stream"""
        try:
            self.audio_stream = self.pa.open(
                rate=self.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.frame_length
            )
            print(f"🎧 Listening for '{self.wake_word}'...")
            print("💡 Say the wake word to give a command\n")
        except Exception as e:
            print(f"❌ Error opening audio stream: {e}")
            sys.exit(1)

    def detect_wake_word(self, audio_bytes):
        """Detect wake word from audio data"""
        try:
            if self.wake_recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(self.wake_recognizer.Result())
                text = result.get("text", "").lower()
                if self.debug and text:
                    print(f"[wake] heard: '{text}'")
                return self.wake_word in text
            return False
        except Exception as e:
            if self.debug:
                print(f"Wake word error: {e}")
            return False

    def detect_command(self, audio_bytes):
        """Detect voice command — returns 'work', 'home', or None"""
        try:
            if self.command_recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(self.command_recognizer.Result())
                text = result.get("text", "").lower()
                if self.debug and text:
                    print(f"[command] heard: '{text}'")
                if "start" in text and "work" in text:
                    return "work"
                if "daddy" in text or ("home" in text and "start" not in text):
                    return "home"
            return None
        except Exception as e:
            if self.debug:
                print(f"Command detection error: {e}")
            return None

    def activate(self):
        """Activate command listening mode"""
        self.is_active = True
        self.activation_time = time.time()
        print("\n" + "=" * 60)
        print("✨ FRIDAY ACTIVATED — say your command...")
        print("   🖥️  'Let's start the work' → Claude.ai + ChatGPT + VS Code")
        print("   🎬  'Daddy is home'         → YouTube + Hotstar + Prime")
        print(f"⏱️  You have {self.active_duration} seconds...")
        print("=" * 60 + "\n")
        self.speak("Yes boss, I'm listening")

    def deactivate(self):
        """Deactivate command listening mode — flush recognizers for clean restart"""
        self.is_active = False
        # Flush stale audio from both recognizers so next detection starts fresh
        self.wake_recognizer.FinalResult()
        self.command_recognizer.FinalResult()
        print(f"\n🔇 Back to standby. Say '{self.wake_word}' to activate.\n")

    def _open_url(self, url):
        """Open a URL cross-platform"""
        if self.os_type == "Darwin":
            subprocess.Popen(["open", url])
        elif self.os_type == "Windows":
            subprocess.Popen(["start", url], shell=True)
        elif self.os_type == "Linux":
            subprocess.Popen(["xdg-open", url])

    def _launch_vscode(self):
        """Launch VS Code cross-platform"""
        if self.os_type == "Darwin":
            subprocess.Popen(["open", "-a", "Visual Studio Code"])
        elif self.os_type == "Windows":
            subprocess.Popen(["start", "code"], shell=True)
        elif self.os_type == "Linux":
            subprocess.Popen(["code"])

    def launch_work_apps(self):
        """Open Claude.ai, ChatGPT and VS Code"""
        print("\n💼 WORK MODE — Launching apps...\n")
        self.speak("Starting work mode boss")

        self._open_url("https://claude.ai")
        print("✅ Opened Claude.ai")
        time.sleep(0.5)

        self._open_url("https://chatgpt.com")
        print("✅ Opened ChatGPT")
        time.sleep(0.5)

        self._launch_vscode()
        print("✅ Launched VS Code")

        print("\n✨ Work apps ready!\n")

    def launch_entertainment_apps(self):
        """Open YouTube, Hotstar and Amazon Prime"""
        print("\n🎬 ENTERTAINMENT MODE — Launching apps...\n")
        self.speak("Welcome home boss, entertainment is ready")

        self._open_url("https://youtube.com")
        print("✅ Opened YouTube")
        time.sleep(0.5)

        self._open_url("https://hotstar.com")
        print("✅ Opened Hotstar")
        time.sleep(0.5)

        self._open_url("https://primevideo.com")
        print("✅ Opened Amazon Prime")

        print("\n✨ Entertainment ready!\n")

    def run(self):
        """Main run loop"""
        self.start_audio_stream()

        try:
            while self.running:
                pcm_bytes = self.audio_stream.read(self.frame_length, exception_on_overflow=False)

                if not self.is_active:
                    # STANDBY — listen for wake word
                    if self.detect_wake_word(pcm_bytes):
                        self.activate()
                else:
                    # ACTIVE — listen for command
                    command = self.detect_command(pcm_bytes)

                    if command == "work":
                        self.launch_work_apps()
                        self.deactivate()

                    elif command == "home":
                        self.launch_entertainment_apps()
                        self.deactivate()

                    elif time.time() - self.activation_time > self.active_duration:
                        self.speak("Didn't catch that boss, can you repeat")
                        self.deactivate()

        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.pa:
            self.pa.terminate()
        print("Goodbye!")


def main():
    print("=" * 70)
    print("  🤖 FRIDAY — Voice Assistant Launcher")
    print("=" * 70)
    print("\n🚀 100% LOCAL - No internet needed!")
    print("🗣️  Say 'Friday' → 'Let's start the work' → Work apps")
    print("🗣️  Say 'Friday' → 'Daddy is home'        → Entertainment apps")
    print("\nPress Ctrl+C to exit\n")

    debug_mode = "--debug" in sys.argv

    # Get wake word from command line or use default
    wake_word = "friday"
    for i, arg in enumerate(sys.argv):
        if arg == "--wake" and i + 1 < len(sys.argv):
            wake_word = sys.argv[i + 1]

    # Get model path from command line or use default
    model_path = "model"
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model_path = sys.argv[i + 1]

    if not debug_mode:
        print("💡 Tip: Run with '--debug' to see what Friday hears")
        print("💡 Tip: Run with '--model vosk-model-en-us-0.22' to use a larger model\n")

    launcher = FridayLauncher(wake_word=wake_word, debug=debug_mode, model_path=model_path)
    launcher.run()


if __name__ == "__main__":
    main()
