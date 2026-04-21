"""
friday_tray.pyw
───────────────
System-tray icon to Start / Stop Friday Assistant.
Saved as .pyw → runs via pythonw.exe (no console window).

Fix summary vs previous version:
  - icon.icon / icon.title / icon.update_menu() now called correctly
  - status label refreshes after every state change
  - watchdog detects when the process dies and syncs the icon
  - disabled menu item uses None action (not lambda: None)
  - all subprocess errors are caught and written to friday_tray_error.log
"""

import os
import sys
import subprocess
import threading
import time
import datetime
import traceback
from pathlib import Path

# ── Auto-install deps ─────────────────────────────────────────────────────────
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "pystray", "pillow", "--quiet"]
    )
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT   = Path(r"C:\Users\malya\.vscode\python practise\Friday\wake-up")
BAT_FILE  = PROJECT / "start_friday.bat"
LOG_FILE  = PROJECT / "friday_startup.log"
ERR_LOG   = PROJECT / "friday_tray_error.log"

# ── Logging ───────────────────────────────────────────────────────────────────
def _log(msg: str):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ERR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

# ── State ─────────────────────────────────────────────────────────────────────
friday_process: subprocess.Popen | None = None
_icon_ref: pystray.Icon | None = None     # set once icon is created


def _is_running() -> bool:
    return friday_process is not None and friday_process.poll() is None


# ── Icon drawing ──────────────────────────────────────────────────────────────
def _make_icon(running: bool) -> Image.Image:
    SIZE = 64
    img  = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)

    bg = (30, 180, 80) if running else (100, 100, 100)   # green / grey
    d.ellipse([4, 4, SIZE - 4, SIZE - 4], fill=bg, outline=(255, 255, 255), width=3)

    # Simple mic shape
    d.rounded_rectangle([24, 12, 40, 36], radius=7, fill=(255, 255, 255))
    d.arc([16, 26, 48, 46], start=0, end=180, fill=(255, 255, 255), width=3)
    d.rectangle([30, 46, 34, 54], fill=(255, 255, 255))
    d.rectangle([24, 53, 40, 57], fill=(255, 255, 255))

    return img


# ── Refresh tray after any state change ───────────────────────────────────────
def _refresh():
    """Update icon image, tooltip and menu — must be called after state changes."""
    if _icon_ref is None:
        return
    try:
        _icon_ref.icon  = _make_icon(_is_running())
        _icon_ref.title = "Friday  ●  Running" if _is_running() else "Friday  ○  Stopped"
        _icon_ref.update_menu()   # ← this is what was missing before
    except Exception as e:
        _log(f"_refresh error: {e}")


# ── Start / Stop ──────────────────────────────────────────────────────────────
def start_friday(icon=None, menu_item=None):
    global friday_process

    if _is_running():
        _log("start_friday called but already running")
        return

    if not BAT_FILE.exists():
        _log(f"BAT_FILE not found: {BAT_FILE}")
        return

    try:
        friday_process = subprocess.Popen(
            ["cmd.exe", "/c", str(BAT_FILE)],
            cwd=str(PROJECT),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        _log(f"Started Friday (PID {friday_process.pid})")
        _refresh()
    except Exception as e:
        _log(f"Failed to start Friday: {e}\n{traceback.format_exc()}")


def stop_friday(icon=None, menu_item=None):
    global friday_process

    if not _is_running():
        _log("stop_friday called but not running")
        return

    try:
        friday_process.terminate()
        try:
            friday_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            friday_process.kill()
        _log("Friday stopped by user")
    except Exception as e:
        _log(f"Error stopping Friday: {e}")
    finally:
        friday_process = None
        _refresh()


def quit_tray(icon, menu_item):
    stop_friday()
    icon.stop()


# ── Dynamic menu labels ───────────────────────────────────────────────────────
def _status_label(_item=None) -> str:
    return "● Running" if _is_running() else "○ Stopped"


def _start_label(_item=None) -> str:
    return "▶  Start Friday" if not _is_running() else "▶  Start Friday (already on)"


# ── Open log ──────────────────────────────────────────────────────────────────
def open_log(icon=None, menu_item=None):
    target = LOG_FILE if LOG_FILE.exists() else ERR_LOG
    if target.exists():
        os.startfile(str(target))
    else:
        _log("open_log: no log file found yet")


# ── Watchdog — syncs icon if process dies on its own ─────────────────────────
def _watchdog():
    global friday_process
    while True:
        time.sleep(4)
        if friday_process is not None and friday_process.poll() is not None:
            # Process ended on its own (crash or normal exit)
            exit_code = friday_process.returncode
            _log(f"Friday process ended (exit code {exit_code})")
            friday_process = None
            _refresh()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _icon_ref

    _log("Tray app started")

    menu = pystray.Menu(
        item(_status_label,    None,         enabled=False),   # live status line
        pystray.Menu.SEPARATOR,
        item(_start_label,     start_friday),                  # Start
        item("■  Stop Friday",  stop_friday),                  # Stop
        pystray.Menu.SEPARATOR,
        item("📄  Open Log",   open_log),
        pystray.Menu.SEPARATOR,
        item("✖  Quit Tray",  quit_tray),
    )

    _icon_ref = pystray.Icon(
        name  = "Friday",
        icon  = _make_icon(False),
        title = "Friday  ○  Stopped",
        menu  = menu,
    )

    # Start watchdog thread
    threading.Thread(target=_watchdog, daemon=True).start()

    # Auto-start Friday 2 s after tray appears
    threading.Timer(2.0, lambda: start_friday(_icon_ref)).start()

    _icon_ref.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log(f"FATAL tray error:\n{traceback.format_exc()}")
