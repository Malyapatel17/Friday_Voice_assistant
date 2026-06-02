# Friday JARVIS-Style Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tkinter corner-orb HUD, conversational Ask mode (GroqChat), voice notes, and a cross-cutting JARVIS personality layer to Friday, on a new `staging/jarvis-features` branch off `main`.

**Architecture:**
- Tkinter HUD owns the main thread (`mainloop()`); `FridayCore.run()` moves to a background daemon thread.
- A single `queue.Queue` of `{"event": ..., "payload": ...}` dicts crosses the boundary — FridayCore `put()`s, HUD drains via `root.after(50, ...)`.
- Three subagents author in parallel; **merge order is strictly A → B → C** because B and C both extend `audio.py:parse_command` and C depends on B's `(token, payload)` tuple return shape.

**Tech Stack:** Python 3 (existing `.venv`), Tkinter (stdlib), `groq` + `python-dotenv` (new), existing `vosk` / `faster-whisper` / `pyttsx3` / `pygame` / `pyaudio`.

**Spec reference:** `docs/superpowers/specs/2026-06-02-friday-jarvis-features-design.md`.

**Testing model:** Per repo CLAUDE.md ("no tests, lints, or build steps configured"), every task uses a **manual verification step** instead of a unit test. The engineer runs Friday and exercises the feature; the step says exactly what to look for.

---

## File map

**Create:**
- `friday/hud.py` — HUD window, state machine, animator (Agent A)
- `friday/personality.py` — wake-word acks, time-of-day greet (Agent B)
- `friday/notes.py` — append + read today's markdown notes file (Agent C)

**Modify:**
- `friday/config.py` — HUD constants (A), `GROQ_MODEL` (B), `NOTES_DIR` (C)
- `friday/audio.py` — `parse_command` adds `"ask"` token + tuple return (B), adds `note_start` / `note_read` (C)
- `friday/conversation.py` — rewrite `SYSTEM_PROMPT` in JARVIS tone (B)
- `main.py` — restructure for HUD/thread/queue (A), add `_on_ask` + personality wiring (B), add `_on_note_start` / `_on_note_read` (C)
- `requirements.txt` — add `groq`, `python-dotenv` (B)
- `.gitignore` — add `/notes/`, `.env` (C)

**No tests directory.** No `tests/` folder created.

---

## Task 0: Create the staging branch (one-shot, before agents start)

**Files:** none directly — git only.

- [ ] **Step 1: Verify clean checkout on main**

Run:
```powershell
git status --short
git rev-parse --abbrev-ref HEAD
```

Expected output: working tree may show pre-existing modifications (`.gitignore`, `friday/audio.py`, `main.py`, `start_friday.bat`, `CLAUDE.md`) — these are **pre-existing** and must be left as-is per prior user instruction. Current branch must be `main`. If you are not on `main`, abort and ask the user.

- [ ] **Step 2: Pull latest main and create branch**

Run:
```powershell
git pull --ff-only origin main; if ($?) { git checkout -b staging/jarvis-features }
```

If `git pull` fails because there is no `origin` or the branch is behind in a way that can't fast-forward, skip the pull and just create the branch from local HEAD: `git checkout -b staging/jarvis-features`.

Expected: new branch `staging/jarvis-features` created and checked out. Pre-existing uncommitted modifications travel with the branch — that is intentional.

- [ ] **Step 3: Verify branch**

Run:
```powershell
git rev-parse --abbrev-ref HEAD
```

Expected output: `staging/jarvis-features`.

- [ ] **Step 4: Commit nothing yet**

No commit. Branch is created; first commits come from Agent A.

---

# Agent A — HUD + Concurrency Refactor

**Owns:** `friday/hud.py` (new), `friday/config.py` (HUD constants), `main.py` (restructure).
**Must merge first.** B and C build on A's `main.py` shape.

## Task A1: Add HUD constants to `friday/config.py`

**Files:**
- Modify: `friday/config.py` (append at end)

- [ ] **Step 1: Append HUD constants**

Open `friday/config.py`. Append the following at the end, leaving the existing content untouched:

```python

# ─────────────────────────────────────────────
# HUD (JARVIS-style corner orb)
# ─────────────────────────────────────────────
HUD_MARGIN_PX        = 24
HUD_ORB_SIZE_PX      = 180
HUD_TEXT_HEIGHT_PX   = 80
HUD_WINDOW_W         = HUD_ORB_SIZE_PX + 40   # canvas padding
HUD_WINDOW_H         = HUD_ORB_SIZE_PX + HUD_TEXT_HEIGHT_PX
HUD_FADE_DELAY_SEC   = 3.0
HUD_IDLE_ALPHA       = 0.40
HUD_ACTIVE_ALPHA     = 1.00
HUD_TRANSPARENT_KEY  = "#010203"   # Windows transparentcolor sentinel
HUD_FRAME_INTERVAL_MS = 33          # ~30 fps
HUD_QUEUE_POLL_MS     = 50          # event-queue drain cadence
HUD_RING_COLOR_IDLE   = "#446677"
HUD_RING_COLOR_ACTIVE = "#33ccff"
HUD_RING_COLOR_ERROR  = "#ff4444"
HUD_TEXT_COLOR        = "#cceeff"
```

- [ ] **Step 2: Manual verification**

Run:
```powershell
.\.venv\Scripts\python.exe -c "import friday.config as c; print(c.HUD_ORB_SIZE_PX, c.HUD_TRANSPARENT_KEY)"
```

Expected output: `180 #010203` (or whatever the exact values are). No `ImportError`, no `AttributeError`.

- [ ] **Step 3: Commit**

```powershell
git add friday/config.py
git commit -m "config: add HUD constants for JARSIS corner-orb overlay`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

(Note the backtick-n inside the double-quoted PowerShell string produces a real newline.)

---

## Task A2: Create `friday/hud.py` — HUD class with idle state only

We build the HUD in two passes: **A2 builds the static idle window** (so it can be visually verified standalone). **A3 adds the state machine, event queue, and animator.**

**Files:**
- Create: `friday/hud.py`

- [ ] **Step 1: Write the file**

Create `friday/hud.py` with the following content:

```python
"""
friday/hud.py
-------------
JARVIS-style corner-orb HUD for Friday.

Windows-only (uses Tk's '-transparentcolor' attribute for the see-through
background, which has no equivalent on macOS/Linux).

Runs on the main thread. FridayCore (background thread) communicates by
putting event dicts on a queue.Queue. The HUD drains the queue from a
Tk after() callback.
"""

import tkinter as tk
from queue import Empty
from typing import Optional

from friday import config as cfg


class FridayHUD:
    """Top-right corner orb. State machine + animator driven by an event queue."""

    # State names (also used as values of self.state).
    IDLE      = "idle"
    WAKE      = "wake"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"
    NOTING    = "noting"
    ERROR     = "error"
    FADING    = "fading"

    def __init__(self, root: tk.Tk, event_queue):
        self.root        = root
        self.event_queue = event_queue
        self.state       = self.IDLE
        self.frame       = 0          # animator tick counter
        self.fade_until  = 0.0        # frame at which to return to IDLE
        self._transcript = ""
        self._reply      = ""
        self._label      = "FRIDAY"

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.wm_attributes("-transparentcolor", cfg.HUD_TRANSPARENT_KEY)
        self.win.wm_attributes("-alpha", cfg.HUD_IDLE_ALPHA)
        self.win.configure(bg=cfg.HUD_TRANSPARENT_KEY)

        # Position top-right of primary monitor.
        sw = self.win.winfo_screenwidth()
        x  = sw - cfg.HUD_WINDOW_W - cfg.HUD_MARGIN_PX
        y  = cfg.HUD_MARGIN_PX
        self.win.geometry(f"{cfg.HUD_WINDOW_W}x{cfg.HUD_WINDOW_H}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.win,
            width=cfg.HUD_WINDOW_W,
            height=cfg.HUD_WINDOW_H,
            bg=cfg.HUD_TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._draw_static()

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def _draw_static(self):
        """Initial static draw. Animator updates this every frame."""
        self.canvas.delete("all")
        cx = cfg.HUD_WINDOW_W // 2
        cy = cfg.HUD_ORB_SIZE_PX // 2 + 10
        r  = cfg.HUD_ORB_SIZE_PX // 2 - 8

        ring_color = cfg.HUD_RING_COLOR_IDLE
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                outline=ring_color, width=3)
        self.canvas.create_text(cx, cy, text=self._label,
                                fill=cfg.HUD_TEXT_COLOR,
                                font=("Consolas", 14, "bold"))


def make_hud(root: tk.Tk, event_queue) -> FridayHUD:
    """Convenience factory called from main.py."""
    return FridayHUD(root, event_queue)
```

- [ ] **Step 2: Standalone visual check**

Run:
```powershell
.\.venv\Scripts\python.exe -c @'
import queue, tkinter as tk
from friday.hud import make_hud
root = tk.Tk()
root.withdraw()              # hide the empty root window
q = queue.Queue()
hud = make_hud(root, q)
root.after(3000, root.destroy)   # auto-close after 3s
root.mainloop()
'@
```

Expected: a small transparent window appears top-right of your primary monitor for 3 seconds, showing a thin gray ring with "FRIDAY" text inside, ~40% opacity. Background between the ring strokes is see-through. Window closes automatically.

If you see a solid black rectangle instead of see-through: the `-transparentcolor` attribute didn't apply. Verify Windows version (Windows 10+ required) and check that `cfg.HUD_TRANSPARENT_KEY` is the exact same value used for both the toplevel and canvas `bg`.

- [ ] **Step 3: Commit**

```powershell
git add friday/hud.py
git commit -m "hud: scaffold FridayHUD class with idle-state render`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task A3: Add state machine, event queue, and animator to HUD

**Files:**
- Modify: `friday/hud.py` (extend `FridayHUD`)

- [ ] **Step 1: Add event constants at module top**

Open `friday/hud.py`. Just below the docstring and imports, before `class FridayHUD`, insert:

```python
# Event types put on the queue by FridayCore. See spec §2.2.
EVT_WAKE_DETECTED  = "wake_detected"
EVT_PARTIAL        = "partial"
EVT_COMMAND_FINAL  = "command_final"
EVT_THINKING       = "thinking"
EVT_SPEAKING_START = "speaking_start"
EVT_SPEAKING_END   = "speaking_end"
EVT_NOTING         = "noting"
EVT_NOTE_SAVED     = "note_saved"
EVT_ERROR          = "error"
EVT_SHUTDOWN       = "shutdown"
```

- [ ] **Step 2: Add `start()` and animator methods to `FridayHUD`**

Inside the `FridayHUD` class, after `_draw_static`, add these methods:

```python
    # ── Public lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Begin animator and event-queue draining loops."""
        self._tick()
        self._drain_queue()

    def stop(self):
        """Tear down the HUD window. Safe to call multiple times."""
        try:
            self.win.destroy()
        except Exception:
            pass

    # ── Animator (runs on Tk main thread) ─────────────────────────────────────

    def _tick(self):
        self.frame += 1
        self._redraw()
        self.root.after(cfg.HUD_FRAME_INTERVAL_MS, self._tick)

    def _redraw(self):
        self.canvas.delete("all")
        cx = cfg.HUD_WINDOW_W // 2
        cy = cfg.HUD_ORB_SIZE_PX // 2 + 10
        r  = cfg.HUD_ORB_SIZE_PX // 2 - 8

        # Ring color per state.
        if self.state == self.ERROR:
            ring = cfg.HUD_RING_COLOR_ERROR
        elif self.state in (self.IDLE, self.FADING):
            ring = cfg.HUD_RING_COLOR_IDLE
        else:
            ring = cfg.HUD_RING_COLOR_ACTIVE

        # WAKE pulses the ring outward briefly.
        pulse = 0
        if self.state == self.WAKE:
            pulse = max(0, 8 - (self.frame % 30) // 2)

        self.canvas.create_oval(cx - r - pulse, cy - r - pulse,
                                cx + r + pulse, cy + r + pulse,
                                outline=ring, width=3)

        # Inner glow during active states.
        if self.state not in (self.IDLE, self.FADING):
            inner = r - 12
            self.canvas.create_oval(cx - inner, cy - inner,
                                    cx + inner, cy + inner,
                                    outline=ring, width=1)

        # Center content per state.
        if self.state in (self.IDLE, self.FADING, self.WAKE):
            self.canvas.create_text(cx, cy, text=self._label,
                                    fill=cfg.HUD_TEXT_COLOR,
                                    font=("Consolas", 14, "bold"))
        elif self.state == self.THINKING:
            # Orbiting dot: position on inner ring by frame angle.
            import math
            angle = (self.frame * 12) % 360
            ox = cx + int((r - 18) * math.cos(math.radians(angle)))
            oy = cy + int((r - 18) * math.sin(math.radians(angle)))
            self.canvas.create_oval(ox - 4, oy - 4, ox + 4, oy + 4,
                                    fill=cfg.HUD_RING_COLOR_ACTIVE, outline="")
            self.canvas.create_text(cx, cy, text="...",
                                    fill=cfg.HUD_TEXT_COLOR,
                                    font=("Consolas", 14, "bold"))
        elif self.state in (self.SPEAKING, self.LISTENING, self.NOTING):
            # 9 vertical bars from a sinusoidal table.
            import math
            for i in range(9):
                bar_x = cx - 36 + i * 9
                phase = (self.frame * 0.4) + i * 0.6
                height = int(8 + 14 * abs(math.sin(phase)))
                self.canvas.create_rectangle(
                    bar_x, cy - height // 2, bar_x + 5, cy + height // 2,
                    fill=cfg.HUD_RING_COLOR_ACTIVE, outline=""
                )

        # Transcript / reply text below the orb.
        text_y = cfg.HUD_ORB_SIZE_PX + 20
        if self._transcript:
            self.canvas.create_text(cx, text_y, text=self._transcript,
                                    fill=cfg.HUD_TEXT_COLOR,
                                    font=("Consolas", 10),
                                    width=cfg.HUD_WINDOW_W - 16)
        elif self._reply:
            self.canvas.create_text(cx, text_y, text=self._reply,
                                    fill=cfg.HUD_TEXT_COLOR,
                                    font=("Consolas", 10),
                                    width=cfg.HUD_WINDOW_W - 16)

        # Auto-fade back to IDLE after speaking_end / note_saved.
        if self.state == self.FADING and self.frame >= self.fade_until:
            self._go_idle()

    # ── Event queue draining (also on main thread) ────────────────────────────

    def _drain_queue(self):
        try:
            while True:
                evt = self.event_queue.get_nowait()
                self._handle_event(evt)
        except Empty:
            pass
        self.root.after(cfg.HUD_QUEUE_POLL_MS, self._drain_queue)

    def _handle_event(self, evt: dict):
        kind    = evt.get("event")
        payload = evt.get("payload") or {}

        if kind == EVT_WAKE_DETECTED:
            self.state = self.WAKE
            self._transcript = ""
            self._reply = ""
            self.win.wm_attributes("-alpha", cfg.HUD_ACTIVE_ALPHA)
            # Drop into LISTENING after the pulse burns through ~600ms.
            self.root.after(600, lambda: self._set_state(self.LISTENING))
        elif kind == EVT_PARTIAL:
            self.state = self.LISTENING
            self._transcript = payload.get("text", "")
        elif kind == EVT_COMMAND_FINAL:
            self._transcript = payload.get("text", "")
            # Stay in LISTENING; dispatch will follow with thinking/speaking.
        elif kind == EVT_THINKING:
            self.state = self.THINKING
            self._transcript = ""
        elif kind == EVT_SPEAKING_START:
            self.state = self.SPEAKING
            self._reply = payload.get("text", "")
            self._transcript = ""
        elif kind == EVT_SPEAKING_END:
            self._begin_fade()
        elif kind == EVT_NOTING:
            self.state = self.NOTING
            self._transcript = ""
            self._reply = ""
        elif kind == EVT_NOTE_SAVED:
            self._reply = f"Saved ({payload.get('count', 0)} today)"
            self._begin_fade()
        elif kind == EVT_ERROR:
            self.state = self.ERROR
            self._reply = payload.get("text", "")
            self.root.after(5000, self._begin_fade)
        elif kind == EVT_SHUTDOWN:
            self.stop()

    def _set_state(self, new_state: str):
        # Deferred WAKE -> LISTENING transition. Only honor it if we are
        # still in WAKE -- otherwise a SPEAKING/THINKING/etc state that the
        # bg thread set in the meantime would be wrongly overwritten.
        if self.state == self.WAKE:
            self.state = new_state

    def _begin_fade(self):
        self.state = self.FADING
        fade_frames = int(cfg.HUD_FADE_DELAY_SEC * 1000 / cfg.HUD_FRAME_INTERVAL_MS)
        self.fade_until = self.frame + fade_frames

    def _go_idle(self):
        self.state       = self.IDLE
        self._transcript = ""
        self._reply      = ""
        self.win.wm_attributes("-alpha", cfg.HUD_IDLE_ALPHA)
```

- [ ] **Step 3: Standalone state-machine test**

Run:
```powershell
.\.venv\Scripts\python.exe -c @'
import queue, tkinter as tk
from friday.hud import make_hud, EVT_WAKE_DETECTED, EVT_PARTIAL, EVT_THINKING, EVT_SPEAKING_START, EVT_SPEAKING_END
root = tk.Tk()
root.withdraw()
q = queue.Queue()
hud = make_hud(root, q)
hud.start()

def push(evt, payload=None, delay=0):
    root.after(delay, lambda: q.put({"event": evt, "payload": payload}))

push(EVT_WAKE_DETECTED, delay=500)
push(EVT_PARTIAL, {"text": "start work"}, delay=1500)
push(EVT_THINKING, delay=2500)
push(EVT_SPEAKING_START, {"text": "Starting work mode boss"}, delay=3500)
push(EVT_SPEAKING_END, delay=5500)

root.after(10000, root.destroy)
root.mainloop()
'@
```

Expected behaviour over ~10 seconds:
1. Idle gray ring with "FRIDAY" text (first 500 ms).
2. Cyan pulse — ring expands and contracts (~600 ms).
3. Listening — bright cyan ring with 9 animated bars; transcript "start work" below.
4. Thinking — bright cyan ring with orbiting dot and "..." in centre.
5. Speaking — bright cyan ring with bars; reply "Starting work mode boss" below.
6. Fade to idle after 3 s.

If any state looks wrong, fix the `_redraw` branch for that state before moving on.

- [ ] **Step 4: Commit**

```powershell
git add friday/hud.py
git commit -m "hud: add state machine, event queue, and 30fps animator`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task A4: Refactor `main.py` — Tk root + bg thread + event queue

This is the load-bearing change. After this task, **Friday's existing four verbs (`work` / `home` / `close_tabs` / `rest`) must still work end-to-end**, just now with the HUD visible.

**Files:**
- Modify: `main.py` (substantial restructure)

- [ ] **Step 1: Read current `main.py`**

Read the file first (it is small, ~200 lines). Understand the current entry point shape before editing.

- [ ] **Step 2: Replace `main.py` contents**

Overwrite `main.py` with the following. Pre-existing local modifications to this file will be carried into the same commit (per prior user direction — leave existing local edits as-is, just be cleaner from here):

```python
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

    # ── HUD event helper ──────────────────────────────────────────────────────

    def _emit(self, event: str, payload: dict | None = None):
        try:
            self.event_queue.put({"event": event, "payload": payload})
        except Exception:
            pass  # never let HUD wiring break the core loop

    # ── Helpers ───────────────────────────────────────────────────────────────

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

    # ── Standby handler ───────────────────────────────────────────────────────

    def _handle_standby(self, frame: bytes):
        if self.audio.detect_wake_word(frame):
            self._emit(EVT_WAKE_DETECTED)
            self._go(COMMAND)
            print("\n" + "=" * 55)
            print("FRIDAY ACTIVATED -- say your command")
            print("=" * 55 + "\n")
            self._speak("Yes boss, I'm listening")

    # ── Command handler ───────────────────────────────────────────────────────

    def _handle_command(self):
        if time.time() - self.cmd_start > cfg.ACTIVE_DURATION:
            self._speak("Didn't catch that boss, say Friday to try again")
            self._go(STANDBY)
            return

        audio = self.audio.record_command()
        text  = self.audio.transcribe_command(audio)
        self._emit(EVT_COMMAND_FINAL, {"text": text})
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
            if self.debug and text:
                print(f"[no match] '{text}'")

    # ── Main loop ─────────────────────────────────────────────────────────────

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


# ── Entry point ───────────────────────────────────────────────────────────────

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
        try:
            core.run()
        finally:
            if root is not None:
                root.after(0, root.destroy)

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
```

- [ ] **Step 3: Manual verification — HUD plus existing verb regression**

This must be run interactively at the user's machine. Run:
```powershell
.\.venv\Scripts\python.exe main.py --debug
```

Expected:
1. Console prints `FRIDAY  --  Voice Assistant  (Phase 1 + HUD)` banner.
2. Within 2 seconds: HUD orb appears top-right, idle gray, ~40% opacity.
3. Console prints `Listening for wake word 'friday' ...`.
4. Say **"Friday"**. HUD pulses cyan. TTS says "Yes boss, I'm listening".
5. Say **"start work"**. HUD shows live partial transcript below the orb, then speaks "Starting work mode boss", then opens Gmail / Claude / ChatGPT / VS Code (per existing launcher).
6. HUD fades back to idle gray within 3 seconds after speaking ends.
7. Press Ctrl+C in the console. HUD window closes within ~7 seconds. Process exits cleanly.

If the HUD doesn't appear, or any of the four verbs regress, **do not commit**. Find and fix the issue first.

- [ ] **Step 4: Headless mode regression check**

Run:
```powershell
.\.venv\Scripts\python.exe main.py --no-hud --debug
```

Expected: same console behaviour as before this branch (no HUD window). Confirms the refactor preserves a headless path. Ctrl+C to exit.

- [ ] **Step 5: Commit**

```powershell
git add main.py
git commit -m "main: move FridayCore to bg thread, mount HUD on main thread`n`nIPC via queue.Queue. Adds --no-hud flag for headless runs.`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task A5: Tray-launch regression check (visual only, no code change)

The tray spawns Friday in a detached console via `start_friday.bat`. Verify HUD still appears under that launch path.

**Files:** none.

- [ ] **Step 1: Launch via tray**

If `friday_tray.pyw` is not already running, double-click the Friday desktop shortcut. Wait for the auto-start (30 s after tray loads — per previous spec) **or** right-click tray → Start Friday.

- [ ] **Step 2: Verify**

Expected:
- New `start_friday.bat` console window appears.
- HUD orb appears top-right within ~3 s of the BAT console opening.
- Wake word + one verb works end-to-end.
- Right-click tray → Stop Friday: BAT console closes, HUD window closes.

If the HUD does not appear under the tray launch but does under direct `python.exe main.py`, suspect the working-directory difference (tray spawns the BAT detached). Check `friday_startup.log` and `friday_tray_error.log` for clues. Do not commit a fix yet — file an issue for Agent A's follow-up.

- [ ] **Step 3: Commit nothing**

No code change in A5. Pure verification.

---

**End of Agent A.** B and C may now author in parallel; B must merge before C.

---

# Agent B — Ask Mode + Personality

**Owns:** `friday/personality.py` (new), `friday/conversation.py` (rewrite prompt), `friday/audio.py` (extend `parse_command` to tuple), `friday/config.py` (add `GROQ_MODEL`), `requirements.txt`, `main.py` (add `_on_ask`, swap wake ack, add greeting + dotenv).

**Must merge after Agent A.**

## Task B1: Add `groq` + `python-dotenv` to `requirements.txt`

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current `requirements.txt`**

Verify it contains pyaudio, vosk, faster-whisper, pyttsx3, pygame (per CLAUDE.md).

- [ ] **Step 2: Append the two new deps**

Append at end of file (one per line):

```
groq
python-dotenv
```

- [ ] **Step 3: Install into the existing venv**

```powershell
.\.venv\Scripts\pip.exe install groq python-dotenv
```

Expected: both install cleanly. Note the installed versions for the commit message.

- [ ] **Step 4: Smoke import**

```powershell
.\.venv\Scripts\python.exe -c "import groq, dotenv; print('groq', groq.__version__); print('dotenv ok')"
```

Expected: prints the groq version (e.g. `groq 0.x.y`) and `dotenv ok`. No `ImportError`.

- [ ] **Step 5: Commit**

```powershell
git add requirements.txt
git commit -m "deps: add groq + python-dotenv for Ask mode`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task B2: Add `GROQ_MODEL` to `friday/config.py`

**Files:**
- Modify: `friday/config.py` (append)

- [ ] **Step 1: Append**

Append at end of `friday/config.py`:

```python

# ─────────────────────────────────────────────
# Ask mode (GroqChat)
# ─────────────────────────────────────────────
import os as _os
GROQ_MODEL = _os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
```

The env-var override lets you test other Groq models without editing code.

- [ ] **Step 2: Manual verification**

```powershell
.\.venv\Scripts\python.exe -c "import friday.config as c; print(c.GROQ_MODEL)"
```

Expected: `llama-3.1-8b-instant`.

- [ ] **Step 3: Commit**

```powershell
git add friday/config.py
git commit -m "config: add GROQ_MODEL with env-var override`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task B3: Rewrite `SYSTEM_PROMPT` in `friday/conversation.py`

**Files:**
- Modify: `friday/conversation.py`

- [ ] **Step 1: Replace the existing `SYSTEM_PROMPT` constant**

Open `friday/conversation.py`. Locate the existing `SYSTEM_PROMPT = (...)` block at lines 7-12. Replace it with:

```python
SYSTEM_PROMPT = (
    "You are Friday, a witty, concise AI assistant in the spirit of "
    "Tony Stark's JARVIS. Speak to the user as 'boss' or 'sir'. "
    "Keep replies short and natural for voice output -- no markdown, "
    "no lists, no bullet points. Maximum three sentences. "
    "Mild dry humour is welcome; do not over-explain. "
    "If you do not know something, say so briefly."
)
```

Leave the rest of `conversation.py` (the `check_internet` function and the `GroqChat` class) untouched.

- [ ] **Step 2: Manual verification**

```powershell
.\.venv\Scripts\python.exe -c "from friday.conversation import SYSTEM_PROMPT; print(SYSTEM_PROMPT[:50])"
```

Expected: prints `You are Friday, a witty, concise AI assistant in t`.

- [ ] **Step 3: Commit**

```powershell
git add friday/conversation.py
git commit -m "conversation: rewrite SYSTEM_PROMPT in JARVIS tone`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task B4: Create `friday/personality.py`

**Files:**
- Create: `friday/personality.py`

- [ ] **Step 1: Write the file**

```python
"""
friday/personality.py
---------------------
Cross-cutting tone helpers: varied wake-word acknowledgements and a
time-of-day greeting. No state; safe to call from any thread.
"""

import datetime
import random

WAKE_ACKS = [
    "Yes boss",
    "I'm listening sir",
    "At your service",
    "Standing by",
    "Go ahead boss",
    "Boss?",
    "How can I help",
    "Right here sir",
]


def wake_ack() -> str:
    """Random short acknowledgement phrase for the wake-word response."""
    return random.choice(WAKE_ACKS)


def greet_for_time_of_day(now: datetime.datetime | None = None) -> str:
    """
    Return a time-of-day greeting.

      05:00 - 11:59 -> "Good morning sir"
      12:00 - 16:59 -> "Good afternoon boss"
      17:00 - 21:59 -> "Good evening sir"
      22:00 - 04:59 -> "You're up late boss"
    """
    now = now or datetime.datetime.now()
    h = now.hour
    if 5 <= h < 12:
        return "Good morning sir"
    if 12 <= h < 17:
        return "Good afternoon boss"
    if 17 <= h < 22:
        return "Good evening sir"
    return "You're up late boss"
```

- [ ] **Step 2: Manual verification**

```powershell
.\.venv\Scripts\python.exe -c @'
from friday.personality import wake_ack, greet_for_time_of_day
import datetime
print(wake_ack())
print(greet_for_time_of_day(datetime.datetime(2026, 6, 2, 9, 0)))
print(greet_for_time_of_day(datetime.datetime(2026, 6, 2, 14, 0)))
print(greet_for_time_of_day(datetime.datetime(2026, 6, 2, 19, 0)))
print(greet_for_time_of_day(datetime.datetime(2026, 6, 2, 23, 30)))
'@
```

Expected:
```
<one of the WAKE_ACKS phrases>
Good morning sir
Good afternoon boss
Good evening sir
You're up late boss
```

- [ ] **Step 3: Commit**

```powershell
git add friday/personality.py
git commit -m "personality: add wake-word acks and time-of-day greeting`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task B5: Change `parse_command` to return `(token, payload)` tuple and add `"ask"`

**This is the breaking signature change.** `main.py` is updated in the same task so the repo never has a broken intermediate state.

**Files:**
- Modify: `friday/audio.py`
- Modify: `main.py`

- [ ] **Step 1: Update `parse_command` in `friday/audio.py`**

Open `friday/audio.py`. Replace the entire `parse_command` static method (currently at lines 209-228) with:

```python
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
```

- [ ] **Step 2: Update `_handle_command` in `main.py`**

Open `main.py`. Find the `_handle_command` method. Replace the single line `cmd = self.audio.parse_command(text)` with:

```python
        cmd, payload = self.audio.parse_command(text)
```

Then add a new `ask` branch in the existing if/elif chain — insert it **after** the `close_tabs` branch and **before** the `rest` branch:

```python
        elif cmd == "ask":
            self._on_ask(payload)
            self._go(STANDBY)
```

- [ ] **Step 3: Add `_on_ask` method to `FridayCore` in `main.py`**

Below `_handle_command`, add this new method:

```python
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
```

- [ ] **Step 4: Manual verification of legacy verbs (regression)**

```powershell
.\.venv\Scripts\python.exe main.py --debug
```

Say each of the four legacy verbs in turn. All must still work exactly as before. (No HUD regression either; A is already merged.)

If any legacy verb regresses, fix `parse_command` ordering before continuing — likely a question word ("what", "do") is matching ahead of an existing verb.

- [ ] **Step 5: Commit**

```powershell
git add friday/audio.py main.py
git commit -m "audio+main: parse_command returns (token, payload); add ask token`n`nLegacy verbs (work/home/close_tabs/rest) preserved by ordering checks`nbefore the implicit question-word trigger.`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task B6: Wire dotenv + greeting + personality wake-ack in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add `dotenv` load at entry**

Open `main.py`. Add this near the top, after the existing imports:

```python
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional at runtime; env vars still work without it
```

- [ ] **Step 2: Add `--no-greeting` CLI handling and the greeting itself**

In `main()`, after `use_hud = "--no-hud" not in sys.argv`, add:

```python
    say_greeting = "--no-greeting" not in sys.argv
```

After `FridayCore(...)` construction succeeds, but before `core_thread.start()`, add (still inside `main()`):

```python
    if say_greeting:
        from friday.personality import greet_for_time_of_day
        # Speak directly via core (not yet on its thread) — fine since the
        # core thread hasn't started, no race with the audio loop.
        core._speak(greet_for_time_of_day())
```

- [ ] **Step 3: Swap the fixed wake ack for the personality variant**

In `_handle_standby`, replace:

```python
            self._speak("Yes boss, I'm listening")
```

with:

```python
            from friday.personality import wake_ack
            self._speak(wake_ack())
```

- [ ] **Step 4: End-to-end Ask manual verification**

Prerequisites: create `.env` next to `main.py` containing `GROQ_API_KEY=<your-key>` from https://console.groq.com.

Run:
```powershell
.\.venv\Scripts\python.exe main.py --debug
```

Expected:
1. Greeting plays at startup (time-of-day appropriate).
2. Say "Friday". HUD pulses cyan, ack heard. The ack varies between runs — try 5 wake-ups in a row; you should see at least three distinct phrases.
3. Say "ask what's the capital of Peru". HUD shows THINKING, then SPEAKING. Friday says something like "The capital of Peru is Lima sir." (JARVIS-tone, ≤3 sentences).
4. Say "Friday" again, then "what is the speed of light". Implicit-ask trigger fires; reply within ~2 s.
5. Two consecutive asks remember context: ask "who is the prime minister of india", then ask "and how old are they" — second reply should reference the first.

Test failure modes:
- Turn off Wi-Fi. Ask. Friday: "I'm offline boss…". HUD goes through THINKING → SPEAKING → IDLE. No crash.
- Rename `.env` temporarily to `.env.bak`. Restart Friday. Ask. Friday: "I need an API key…". No crash.
- Put back `.env`.

If any of these regresses or crashes, fix before committing.

- [ ] **Step 5: Commit**

```powershell
git add main.py
git commit -m "main: load .env, add startup greeting + varied wake acks`n`n--no-greeting flag suppresses the greeting for debugging.`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

**End of Agent B.** Agent C now rebases onto B's HEAD and proceeds.

---

# Agent C — Voice Notes

**Owns:** `friday/notes.py` (new), `friday/audio.py` (extend `parse_command` further), `friday/config.py` (add `NOTES_DIR`), `main.py` (add `_on_note_start` / `_on_note_read`), `.gitignore`.

**Depends on B's tuple signature for `parse_command`.** Must merge after B.

## Task C1: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append**

Append at end of `.gitignore`:

```
/notes/
.env
```

- [ ] **Step 2: Verify**

```powershell
git check-ignore notes/foo.md .env
```

Expected output:
```
notes/foo.md
.env
```

- [ ] **Step 3: Commit**

```powershell
git add .gitignore
git commit -m "gitignore: exclude notes/ and .env`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task C2: Add `NOTES_DIR` to `friday/config.py`

**Files:**
- Modify: `friday/config.py`

- [ ] **Step 1: Append**

Append at end of `friday/config.py`:

```python

# ─────────────────────────────────────────────
# Voice notes
# ─────────────────────────────────────────────
NOTES_DIR = "notes"  # relative to project root (parent of main.py)
```

- [ ] **Step 2: Verify**

```powershell
.\.venv\Scripts\python.exe -c "from friday.config import NOTES_DIR; print(NOTES_DIR)"
```

Expected: `notes`.

- [ ] **Step 3: Commit**

```powershell
git add friday/config.py
git commit -m "config: add NOTES_DIR constant`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task C3: Create `friday/notes.py`

**Files:**
- Create: `friday/notes.py`

- [ ] **Step 1: Write the file**

```python
"""
friday/notes.py
---------------
Append + read today's voice notes. One markdown file per calendar day at
{PROJECT}/{cfg.NOTES_DIR}/YYYY-MM-DD.md.

No edit / delete API. Single-process, single-thread writer (FridayCore
thread). No locking needed.
"""

import datetime
from pathlib import Path

from friday import config as cfg

# Project root is the parent of the friday/ package, i.e. parent of this file's parent.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _today_path(now: datetime.datetime | None = None) -> Path:
    """Return today's notes file path. Creates the parent dir if missing."""
    now = now or datetime.datetime.now()
    dirpath = _PROJECT_ROOT / cfg.NOTES_DIR
    dirpath.mkdir(parents=True, exist_ok=True)
    return dirpath / f"{now.strftime('%Y-%m-%d')}.md"


def append(text: str, now: datetime.datetime | None = None) -> int:
    """Append a note entry. Returns the new total count of entries for today.

    File format:

        # Notes -- 2026-06-02

        - 09:14  buy milk on the way home
        - 11:42  remind anu about the dentist appointment
    """
    text = text.strip()
    if not text:
        return _count_entries(now)

    now = now or datetime.datetime.now()
    path = _today_path(now)

    if not path.exists():
        path.write_text(f"# Notes -- {now.strftime('%Y-%m-%d')}\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {now.strftime('%H:%M')}  {text}\n")

    return _count_entries(now)


def read_today(now: datetime.datetime | None = None) -> list[tuple[str, str]]:
    """Return today's entries as [(HH:MM, text), ...] in file order."""
    path = _today_path(now)
    if not path.exists():
        return []

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        # Format: "- HH:MM  text"
        body = line[2:]
        if len(body) < 8 or body[5] != " " or body[2] != ":":
            continue
        time_str = body[:5]
        text     = body[7:].strip()
        if text:
            entries.append((time_str, text))
    return entries


def _count_entries(now: datetime.datetime | None = None) -> int:
    return len(read_today(now))
```

- [ ] **Step 2: Manual verification**

```powershell
.\.venv\Scripts\python.exe -c @'
from friday import notes
import datetime

t1 = datetime.datetime(2026, 6, 2, 9, 14)
t2 = datetime.datetime(2026, 6, 2, 11, 42)

print("count after first:", notes.append("buy milk on the way home", t1))
print("count after second:", notes.append("remind anu about the dentist appointment", t2))
print("entries:")
for time, text in notes.read_today(t1):
    print(" ", time, text)
'@
```

Expected:
```
count after first: 1
count after second: 2
entries:
  09:14 buy milk on the way home
  11:42 remind anu about the dentist appointment
```

Open `notes/2026-06-02.md` in any editor — confirm the file matches the format shown in the docstring.

Then delete the file so the in-app test below starts clean:
```powershell
Remove-Item "notes\2026-06-02.md" -ErrorAction SilentlyContinue
```

- [ ] **Step 3: Commit**

```powershell
git add friday/notes.py
git commit -m "notes: add append + read_today for daily markdown notes`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task C4: Add `note_start` / `note_read` tokens to `parse_command`

**Files:**
- Modify: `friday/audio.py` (extend `parse_command` — depends on B's tuple signature)

- [ ] **Step 1: Insert note triggers in `parse_command`**

Open `friday/audio.py:parse_command`. **After** the existing `rest` check and **before** the `"ask "` explicit trigger, insert these branches:

```python
        # Voice notes.
        if any(p in t for p in ("take a note", "new note", "make a note",
                                "note this", "remember this")):
            return "note_start", ""
        if any(p in t for p in ("read my notes", "what are my notes",
                                "play my notes", "any notes")):
            return "note_read", ""
```

Notes ordering rationale: legacy verbs run first (so `"close all tabs"` wins even if some future ack contains "note"); note triggers run before "ask" so `"take a note"` doesn't accidentally match the implicit ask question-word path.

- [ ] **Step 2: Manual unit-style check of parse_command**

```powershell
.\.venv\Scripts\python.exe -c @'
from friday.audio import AudioManager as A
for t in ["take a note", "read my notes", "ask what time is it",
          "what time is it", "start work", "daddy is home",
          "close all tabs", "you can rest", "remember this"]:
    print(repr(t), "->", A.parse_command(t))
'@
```

Expected output (exact):
```
'take a note' -> ('note_start', '')
'read my notes' -> ('note_read', '')
'ask what time is it' -> ('ask', 'what time is it')
'what time is it' -> ('ask', 'what time is it')
'start work' -> ('work', '')
'daddy is home' -> ('home', '')
'close all tabs' -> ('close_tabs', '')
'you can rest' -> ('rest', '')
'remember this' -> ('note_start', '')
```

If any line differs, fix the ordering inside `parse_command` before committing.

- [ ] **Step 3: Commit**

```powershell
git add friday/audio.py
git commit -m "audio: add note_start and note_read tokens to parse_command`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task C5: Dispatch notes in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add note branches in `_handle_command`**

In `main.py:_handle_command`, the if/elif chain currently has `work / home / close_tabs / ask / rest`. Add two new branches **before** `rest`:

```python
        elif cmd == "note_start":
            self._on_note_start()
            self._go(STANDBY)
        elif cmd == "note_read":
            self._on_note_read()
            self._go(STANDBY)
```

- [ ] **Step 2: Add `_on_note_start` and `_on_note_read` methods**

Below `_on_ask`, add:

```python
    # ── Voice notes ───────────────────────────────────────────────────────────

    def _on_note_start(self):
        """Capture up to 30s of speech and append to today's notes file."""
        from friday import notes
        from friday.personality import wake_ack

        # Personality variant of "go ahead"
        self._speak("Go ahead boss")

        self._emit(EVT_NOTING)
        audio = self.audio.record_command(max_seconds=30.0, silence_secs=2.0)
        text  = self.audio.transcribe_command(audio)

        if not text:
            self._speak("Didn't catch that boss")
            # _speak already emits SPEAKING_END; no extra event needed.
            return

        try:
            count = notes.append(text)
        except Exception as exc:
            _log_error(f"notes.append failed: {exc}")
            self._speak("Couldn't save the note boss")
            return

        self._speak("Noted boss")
        self._emit(EVT_NOTE_SAVED, {"count": count})

    def _on_note_read(self):
        """Read today's notes back to the user."""
        from friday import notes

        entries = notes.read_today()
        if not entries:
            self._speak("No notes today boss")
            return

        for time_str, text in entries:
            self._speak(f"At {time_str}, {text}")
```

- [ ] **Step 3: End-to-end notes manual verification**

```powershell
.\.venv\Scripts\python.exe main.py --debug
```

Expected:
1. Say "Friday" → "take a note" → "Go ahead boss" heard, HUD shows NOTING with animated bars.
2. Speak a short sentence ("buy milk after work tomorrow"). Wait ~2 s of silence. HUD shows SPEAKING ("Noted boss"), then NOTE_SAVED toast ("Saved (1 today)"), then fades to IDLE.
3. Open `notes/<today>.md` in a text editor — confirm the entry is there in the documented format.
4. Say "Friday" → "read my notes" → Friday speaks the entry as "At HH:MM, buy milk after work tomorrow".
5. Say "Friday" → "read my notes" again (no new notes added) — Friday reads the same entry again. No crash.
6. Edge case: say "Friday" → "take a note" → stay silent for 30 s. Friday says "Didn't catch that boss" and returns to standby. No file written for that empty attempt.

If anything regresses (HUD, legacy verbs, ask mode), fix before committing.

- [ ] **Step 4: Commit**

```powershell
git add main.py
git commit -m "main: dispatch note_start and note_read commands`n`nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

**End of Agent C.**

---

# Task Z: Final integration smoke + push

After all three agents have merged into `staging/jarvis-features`, run the full feature surface end-to-end one more time. **This task is not optional** — it catches any HUD/parse_command/dispatch interaction the per-agent checks miss.

**Files:** none (pure verification).

- [ ] **Step 1: Run Friday under direct python with HUD**

```powershell
.\.venv\Scripts\python.exe main.py --debug
```

Exercise each feature, in this order, from a single Friday process:

1. ✅ Startup greeting plays.
2. ✅ Wake → "start work" → work mode launches.
3. ✅ Wake → "daddy is home" → entertainment launches.
4. ✅ Wake → "ask what's the speed of light" → JARVIS-tone reply.
5. ✅ Wake → "what time is it" → implicit ask works.
6. ✅ Wake → "take a note" → "Go ahead boss" → speak → "Noted boss".
7. ✅ Wake → "read my notes" → reads the note back.
8. ✅ Wake → "close all tabs" → browsers close + shutdown dialog opens. (Cancel the dialog.)
9. ✅ Wake → "you can rest" → Friday speaks goodbye, HUD fades, process exits within 7 s.

The HUD must show the correct state for every interaction (LISTENING → THINKING → SPEAKING → IDLE), with no stale text and no flickering.

- [ ] **Step 2: Run Friday under the tray (pythonw, no console)**

If the tray is not running, double-click the Friday desktop shortcut. Wait for auto-start or right-click → Start Friday.

Run a short verification: wake-word + one Ask + one Note. Confirm:
- HUD appears under tray launch.
- `friday_tray_error.log` contains no new errors.
- `friday_error.log` contains no new tracebacks.

- [ ] **Step 3: Push the branch**

⚠️ **Confirm with the user before pushing.** The system-prompt rule is "Never push to remote without an explicit ask". If the user has not explicitly said to push, stop here and report the state.

If approved:
```powershell
git push -u origin staging/jarvis-features
```

- [ ] **Step 4: Open the PR (optional, if user asks)**

If the user asks for a PR:
```powershell
gh pr create --title "feat: JARVIS HUD + Ask mode + Voice notes + Personality" --body "Implements docs/superpowers/specs/2026-06-02-friday-jarvis-features-design.md. See per-agent commits for details."
```

- [ ] **Step 5: Done**

Report to the user: all features verified end-to-end on `staging/jarvis-features`, branch pushed (if approved), open Task 6 (reboot test from previous spec) still pending the user's separate reboot.

---

## Subagent dispatch summary (for executing-plans / subagent-driven-development)

| Agent | Tasks | Files touched | Independent of |
|-------|-------|---------------|----------------|
| A | A1-A5 | `friday/config.py` (HUD constants only), `friday/hud.py`, `main.py` | — (merges first) |
| B | B1-B6 | `requirements.txt`, `friday/config.py` (GROQ_MODEL), `friday/conversation.py`, `friday/personality.py`, `friday/audio.py`, `main.py` | A already merged |
| C | C1-C5 | `.gitignore`, `friday/config.py` (NOTES_DIR), `friday/notes.py`, `friday/audio.py`, `main.py` | A and B already merged |
| Z | one-shot | none | A + B + C all merged |

**Merge constraint:** A → B → C, strict. C's parse_command change depends on B's tuple signature; both touch the same function and the same `_handle_command` chain in `main.py`.
