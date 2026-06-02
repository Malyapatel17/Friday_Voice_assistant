#!/usr/bin/env python3
"""
Friday -- Voice-Activated Assistant  (Phase 1 + JARVIS HUD)
Run: python main.py [--model path/to/model] [--debug] [--no-hud]

Say "Friday" -> then within 30 seconds say a command:
  "Let's start the work"  ->  Gmail + Claude.ai + ChatGPT + VS Code
  "Daddy is home"         ->  YouTube + Hotstar + Amazon Prime
  "Close all tabs"        ->  Close browsers + shutdown dialog
  "You can rest"          ->  Exit Friday
"""

import platform
import queue
import signal
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path

import friday.config as cfg
from friday.audio import AudioManager
from friday       import launcher
from friday.hud   import (
    make_hud,
    EVT_WAKE_DETECTED, EVT_PARTIAL, EVT_COMMAND_FINAL,
    EVT_THINKING, EVT_SPEAKING_START, EVT_SPEAKING_END,
    EVT_NOTING, EVT_NOTE_SAVED, EVT_ERROR, EVT_SHUTDOWN,
)
from friday.tts   import discover_offline_voice_id, speak

ERROR_LOG = Path(__file__).parent / "friday_error.log"

STANDBY = "standby"
COMMAND = "command"


def _log_error(msg: str):
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


class FridayCore:
    def __init__(self, event_queue: queue.Queue, model_path: str | None = None, debug: bool = False):
        self.event_queue = event_queue
        self.debug   = debug
        self.os_type = platform.system()
        self.running = True

        print("=" * 60)
        print("  FRIDAY  --  Voice Assistant  (Phase 1 + HUD)")
        print("=" * 60)
        print(f"\n  OS : {self.os_type}\n")

        if model_path:
            cfg.MODEL_PATH = model_path

        self.voice_id = discover_offline_voice_id()
        self.audio = AudioManager(
            model_path=cfg.MODEL_PATH,
            wake_word=cfg.WAKE_WORD,
        )

        self.state     = STANDBY
        self.cmd_start = 0.0

        signal.signal(signal.SIGINT, self._on_ctrl_c)

    # -- HUD event helper ------------------------------------------------------

    def _emit(self, event: str, payload: dict | None = None):
        try:
            self.event_queue.put({"event": event, "payload": payload})
        except Exception:
            pass  # never let HUD wiring break the core loop

    # -- Helpers ---------------------------------------------------------------

    def _on_ctrl_c(self, *_):
        print("\n\nShutting down Friday...")
        self.running = False

    def _speak(self, text: str):
        self._emit(EVT_SPEAKING_START, {"text": text})
        speak(
            text,
            audio_stream=self.audio.stream,
            is_online=False,
            offline_voice_id=self.voice_id,
            tts_rate=cfg.TTS_RATE,
        )
        self._emit(EVT_SPEAKING_END)

    def _go(self, new_state: str):
        self.state     = new_state
        self.cmd_start = time.time()
        self.audio.flush()
        if self.debug:
            print(f"[state -> {new_state}]")

    # -- Standby handler -------------------------------------------------------

    def _handle_standby(self, frame: bytes):
        if self.audio.detect_wake_word(frame):
            self._emit(EVT_WAKE_DETECTED)
            self._go(COMMAND)
            print("\n" + "=" * 55)
            print("FRIDAY ACTIVATED -- say your command")
            print("=" * 55 + "\n")
            self._speak("Yes boss, I'm listening")

    # -- Command handler -------------------------------------------------------

    def _handle_command(self):
        if time.time() - self.cmd_start > cfg.ACTIVE_DURATION:
            self._speak("Didn't catch that boss, say Friday to try again")
            self._go(STANDBY)
            return

        audio = self.audio.record_command()
        text  = self.audio.transcribe_command(audio)
        self._emit(EVT_COMMAND_FINAL, {"text": text})
        cmd, payload = self.audio.parse_command(text)

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
        elif cmd == "ask":
            self._on_ask(payload)
            self._go(STANDBY)
        elif cmd == "rest":
            self._speak("Goodbye boss, have a great day")
            self.running = False
        else:
            if self.debug and text:
                print(f"[no match] '{text}'")

    # ── Ask mode (GroqChat) ───────────────────────────────────────────────────

    def _on_ask(self, payload: str):
        """Send payload to GroqChat and speak the reply."""
        from friday.conversation import GroqChat, check_internet
        import os

        if not payload:
            self._speak("Ask me what, boss?")
            return

        self._emit(EVT_THINKING)

        if not check_internet():
            self._speak("I'm offline boss, can't reach my brain right now.")
            return

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            self._speak("I need an API key for that boss, check the readme.")
            return

        if not hasattr(self, "_chat") or self._chat is None:
            try:
                self._chat = GroqChat(api_key=api_key, model=cfg.GROQ_MODEL)
            except Exception as exc:
                _log_error(f"GroqChat init failed: {exc}")
                self._speak("Something went wrong reaching the brain boss.")
                return

        try:
            reply = self._chat.ask(payload)
        except Exception as exc:
            _log_error(f"GroqChat ask failed: {exc}")
            self._speak("Something went wrong reaching the brain boss.")
            return

        self._speak(reply)

    # -- Main loop -------------------------------------------------------------

    def run(self):
        self.audio.start_stream()
        print(f"\nListening for wake word '{cfg.WAKE_WORD}' ...")
        print("Press Ctrl+C to exit\n")
        try:
            while self.running:
                if self.state == STANDBY:
                    frame = self.audio.read_frame()
                    self._handle_standby(frame)
                elif self.state == COMMAND:
                    self._handle_command()
        except KeyboardInterrupt:
            print("\n\nBye!")
        except Exception as exc:
            tb = traceback.format_exc()
            _log_error(f"CRASH in main loop:\n{tb}")
            print(f"\n[ERROR] {type(exc).__name__}: {exc}")
            print(f"Full traceback written to: {ERROR_LOG}")
            traceback.print_exc()
            self._emit(EVT_ERROR, {"text": f"{type(exc).__name__}"})
        finally:
            self.audio.cleanup()
            self._emit(EVT_SHUTDOWN)
            print("Goodbye!")


# -- Entry point ---------------------------------------------------------------

def main():
    debug    = "--debug" in sys.argv
    use_hud  = "--no-hud" not in sys.argv

    model = None
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]

    if not debug:
        print("Tip: run with --debug to see live transcripts\n")

    event_queue: queue.Queue = queue.Queue()

    if use_hud:
        root = tk.Tk()
        root.withdraw()  # keep the empty root window hidden
        hud = make_hud(root, event_queue)
        hud.start()
    else:
        root = None
        hud  = None

    try:
        core = FridayCore(event_queue=event_queue, model_path=model, debug=debug)
    except Exception as exc:
        tb = traceback.format_exc()
        _log_error(f"CRASH at startup:\n{tb}")
        print(f"\n[ERROR] Startup failed: {exc}")
        print(f"Full traceback written to: {ERROR_LOG}")
        traceback.print_exc()
        sys.exit(1)

    def _run_core():
        # core.run()'s own finally emits EVT_SHUTDOWN; the HUD drains that on
        # the main thread and destroys the root, which makes mainloop() return.
        # No cross-thread Tk call here (that would race the EVT_SHUTDOWN path).
        core.run()

    core_thread = threading.Thread(target=_run_core, name="FridayCore", daemon=True)
    core_thread.start()

    if root is not None:
        try:
            root.mainloop()
        finally:
            core.running = False
            core_thread.join(timeout=7)
    else:
        # Headless mode (--no-hud): block on the worker thread.
        try:
            core_thread.join()
        except KeyboardInterrupt:
            core.running = False
            core_thread.join(timeout=7)


if __name__ == "__main__":
    main()
