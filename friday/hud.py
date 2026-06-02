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
