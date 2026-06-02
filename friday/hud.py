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


def make_hud(root: tk.Tk, event_queue) -> FridayHUD:
    """Convenience factory called from main.py."""
    return FridayHUD(root, event_queue)
