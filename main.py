#!/usr/bin/env python3
"""
Friday — Voice-Activated AI Assistant
Run: python main.py [--model path/to/model] [--debug]

Commands after saying 'Friday':
  "Let's start the work" → Opens Claude.ai, ChatGPT, VS Code
  "Daddy is home"        → Opens YouTube, Hotstar, Amazon Prime
  "Let's chat"           → Enters free AI conversation mode (Groq)
"""

import platform
import signal
import sys
import time

import friday.config as config
from friday.audio import AudioManager
from friday.conversation import GroqChat, check_internet
from friday import launcher
from friday.tts import discover_offline_voice_id, speak

# ── States ────────────────────────────────────────────────────────────────────
STANDBY = "standby"
COMMAND = "command"
CHAT = "chat"


class FridayCore:
    def __init__(self, model_path=None, debug=False):
        self.debug = debug
        self.os_type = platform.system()

        print("=" * 70)
        print("  🤖 FRIDAY — Voice AI Assistant")
        print("=" * 70)
        print(f"\n🖥️  Detected OS: {self.os_type}")

        # Override model path if supplied via CLI
        if model_path:
            config.MODEL_PATH = model_path

        # Internet check
        print("🌐 Checking internet connection...")
        self.is_online = check_internet()
        if self.is_online:
            print("   ✅ Online  — Jenny voice + Groq AI active")
        else:
            print("   ❌ Offline — Zira voice, no AI chat")
        print()

        # TTS — discover offline voice once at startup
        self.offline_voice_id = discover_offline_voice_id()

        # Audio / speech recognition
        self.audio = AudioManager(
            model_path=config.MODEL_PATH,
            wake_word=config.WAKE_WORD
        )

        # Groq chat (only if online and API key configured)
        self.groq = None
        if self.is_online and config.GROQ_API_KEY != "YOUR_GROQ_KEY_HERE":
            try:
                self.groq = GroqChat(config.GROQ_API_KEY, config.GROQ_MODEL)
                print("✅ Groq AI ready!")
            except Exception as e:
                print(f"⚠️  Groq init failed: {e}")
        elif self.is_online:
            print("⚠️  Add your Groq API key in friday/config.py to enable chat mode")

        # State machine
        self.state = STANDBY
        self.state_start_time = time.time()
        self.chat_last_activity = 0
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _signal_handler(self, sig, frame):
        print("\n\n👋 Shutting down Friday...")
        self.running = False

    def _speak(self, text):
        speak(
            text,
            audio_stream=self.audio.stream,
            is_online=self.is_online,
            offline_voice_id=self.offline_voice_id,
            tts_rate=config.TTS_RATE
        )

    def _set_state(self, new_state):
        self.state = new_state
        self.state_start_time = time.time()
        self.audio.flush()
        if self.debug:
            print(f"[state] → {new_state}")

    # ── State handlers ────────────────────────────────────────────────────────

    def _handle_standby(self, frame):
        if self.audio.detect_wake_word(frame):
            self._set_state(COMMAND)
            print("\n" + "=" * 60)
            print("✨ FRIDAY ACTIVATED — say your command...")
            print("   🖥️  'Let's start the work'")
            print("   🎬  'Daddy is home'")
            print("   💬  'Let's chat'")
            print("   🔴  'Close all tabs'")
            print("   😴  'You can rest'")
            print(f"⏱️  You have {config.ACTIVE_DURATION} seconds...")
            print("=" * 60 + "\n")
            self._speak("Yes boss, I'm listening")

    def _handle_command(self, frame):
        cmd = self.audio.detect_command(frame)
        elapsed = time.time() - self.state_start_time

        if cmd == "work":
            self._speak("Starting work mode boss")
            launcher.launch_work_apps(self.os_type)
            self._set_state(STANDBY)

        elif cmd == "home":
            self._speak("Welcome home boss, entertainment is ready")
            launcher.launch_entertainment_apps(self.os_type)
            self._set_state(STANDBY)

        elif cmd == "chat":
            if self.is_online and self.groq:
                self._set_state(CHAT)
                self.chat_last_activity = time.time()
                self.groq.reset()
                self._speak("Chat mode on boss, what's on your mind?")
            else:
                self._speak("Sorry boss, no internet connection available for chat")
                self._set_state(STANDBY)

        elif cmd == "close_tabs":
            self._speak("Closing all tabs boss")
            launcher.close_browsers(self.os_type)
            time.sleep(1)
            launcher.open_shutdown_dialog(self.os_type)
            self._set_state(STANDBY)

        elif cmd == "rest":
            self._speak("Goodbye boss, have a great day")
            self.running = False

        elif elapsed > config.ACTIVE_DURATION:
            self._speak("Didn't catch that boss, can you repeat")
            self._set_state(STANDBY)

    def _handle_chat(self, frame):
        text = self.audio.detect_chat_speech(frame)
        inactivity = time.time() - self.chat_last_activity

        if text:
            self.chat_last_activity = time.time()
            if self.debug:
                print(f"[chat] You: {text}")

            if any(w in text.lower() for w in ["goodbye", "stop", "exit", "bye"]):
                self._speak("Goodbye boss, have a great day")
                self._set_state(STANDBY)
                return

            print(f"You: {text}")
            try:
                reply = self.groq.ask(text)
                self._speak(reply)
            except Exception as e:
                print(f"⚠️  Groq error: {e}")
                self._speak("Sorry boss, I couldn't get a response right now")

        elif inactivity > config.CHAT_TIMEOUT:
            self._speak("Going to sleep boss, call me when you need me")
            self._set_state(STANDBY)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        self.audio.start_stream()
        print(f"🎧 Listening for '{config.WAKE_WORD}'...")
        print("💡 Say the wake word to activate\n")

        try:
            while self.running:
                frame = self.audio.read_frame()

                if self.state == STANDBY:
                    self._handle_standby(frame)
                elif self.state == COMMAND:
                    self._handle_command(frame)
                elif self.state == CHAT:
                    self._handle_chat(frame)

        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.audio.cleanup()


def main():
    debug_mode = "--debug" in sys.argv

    model_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model_path = sys.argv[i + 1]

    if not debug_mode:
        print("💡 Tip: Run with '--debug' to see what Friday hears")
        print("💡 Tip: Run with '--model path/to/model' to use a different model\n")

    core = FridayCore(model_path=model_path, debug=debug_mode)
    core.run()


if __name__ == "__main__":
    main()
