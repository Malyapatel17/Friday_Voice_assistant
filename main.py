#!/usr/bin/env python3
"""
Friday — Voice-Activated Assistant  (Phase 1)
Run: python main.py [--model path/to/model] [--debug]

Say "Friday" → then within 30 seconds say a command:
  "Let's start the work"  →  Claude.ai + ChatGPT + VS Code
  "Daddy is home"         →  YouTube + Hotstar + Amazon Prime
  "Close all tabs"        →  Close browsers + shutdown dialog
  "You can rest"          →  Exit Friday
"""

import platform
import signal
import sys
import time

import friday.config as cfg
from friday.audio  import AudioManager
from friday        import launcher
from friday.tts    import discover_offline_voice_id, speak

# ── States ────────────────────────────────────────────────────────────────────
STANDBY = "standby"
COMMAND = "command"


class FridayCore:

    def __init__(self, model_path: str | None = None, debug: bool = False):
        self.debug   = debug
        self.os_type = platform.system()
        self.running = True

        print("=" * 60)
        print("  🤖  FRIDAY  —  Voice Assistant  (Phase 1)")
        print("=" * 60)
        print(f"\n🖥️   OS : {self.os_type}\n")

        # Allow CLI to override model path
        if model_path:
            cfg.MODEL_PATH = model_path

        # Discover offline TTS voice once at startup
        self.voice_id = discover_offline_voice_id()

        # Audio engine (Vosk wake + Whisper commands)
        self.audio = AudioManager(
            model_path=cfg.MODEL_PATH,
            wake_word=cfg.WAKE_WORD,
        )

        # State machine bookkeeping
        self.state      = STANDBY
        self.cmd_start  = 0.0          # when COMMAND state began

        signal.signal(signal.SIGINT, self._on_ctrl_c)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_ctrl_c(self, *_):
        print("\n\n👋 Shutting down Friday...")
        self.running = False

    def _speak(self, text: str):
        speak(
            text,
            audio_stream=self.audio.stream,
            is_online=False,                  # Phase 1: offline only
            offline_voice_id=self.voice_id,
            tts_rate=cfg.TTS_RATE,
        )

    def _go(self, new_state: str):
        """Transition to a new state and flush stale audio buffers."""
        self.state     = new_state
        self.cmd_start = time.time()
        self.audio.flush()
        if self.debug:
            print(f"[state → {new_state}]")

    # ── Standby handler (streaming, frame-by-frame) ───────────────────────────

    def _handle_standby(self, frame: bytes):
        if self.audio.detect_wake_word(frame):
            self._go(COMMAND)
            print("\n" + "=" * 55)
            print("✨ FRIDAY ACTIVATED — say your command:")
            print("   🖥️   'Let's start the work'")
            print("   🎬   'Daddy is home'")
            print("   🔴   'Close all tabs'")
            print("   😴   'You can rest'")
            print(f"⏱️   {cfg.ACTIVE_DURATION} second window")
            print("=" * 55 + "\n")
            self._speak("Yes boss, I'm listening")

    # ── Command handler (blocking record → transcribe → act) ─────────────────

    def _handle_command(self):
        # Timeout guard — if user never speaks, go back to standby
        if time.time() - self.cmd_start > cfg.ACTIVE_DURATION:
            self._speak("Didn't catch that boss, say Friday to try again")
            self._go(STANDBY)
            return

        # Record up to 6 s (stops early on silence)
        audio = self.audio.record_command()
        text  = self.audio.transcribe_command(audio)
        cmd   = self.audio.parse_command(text)

        if cmd == "work":
            self._speak("Starting work mode boss")
            launcher.launch_work_apps(self.os_type)
            self._go(STANDBY)

        elif cmd == "home":
            self._speak("Welcome home boss, entertainment is ready")
            launcher.launch_entertainment_apps(self.os_type)
            self._go(STANDBY)

        elif cmd == "close_tabs":
            self._speak("Closing all tabs boss")
            launcher.close_browsers(self.os_type)
            time.sleep(1)
            launcher.open_shutdown_dialog(self.os_type)
            self._go(STANDBY)

        elif cmd == "rest":
            self._speak("Goodbye boss, have a great day")
            self.running = False

        else:
            # Heard something but didn't match — stay in COMMAND, keep listening
            if self.debug and text:
                print(f"[no match] '{text}'")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        self.audio.start_stream()
        print(f"\n🎧 Listening for wake word  '{cfg.WAKE_WORD}' ...")
        print("💡 Press Ctrl+C to exit\n")

        try:
            while self.running:
                if self.state == STANDBY:
                    frame = self.audio.read_frame()
                    self._handle_standby(frame)
                elif self.state == COMMAND:
                    self._handle_command()     # blocks during recording
        except KeyboardInterrupt:
            print("\n\n👋 Bye!")
        except Exception as exc:
            print(f"\n❌ Unexpected error: {exc}")
            import traceback
            traceback.print_exc()
        finally:
            self.audio.cleanup()
            print("Goodbye!")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    debug = "--debug" in sys.argv

    model = None
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]

    if not debug:
        print("💡 Run with --debug to see live transcripts\n")

    FridayCore(model_path=model, debug=debug).run()


if __name__ == "__main__":
    main()
