"""
friday_tray.pyw
---------------
System-tray icon to Start / Stop Friday Assistant.
Saved as .pyw -> runs via pythonw.exe (no console window).

Fixes in this version:
  - Windows named mutex prevents multiple tray instances from spawning
    (root cause of Friday loading 4-5 times after startup)
  - Tray auto-start removed -- user starts Friday manually from tray
    to avoid race conditions during boot
  - All Unicode symbols replaced with ASCII for PS 5.1 compatibility
"""

import os
import sys
import ctypes
import subprocess
import threading
import time
import datetime
import traceback
from pathlib import Path

# ── Single-instance mutex ─────────────────────────────────────────────────────
# If another tray is already running, this instance exits immediately.
# This is the fix for the "4-5 launches at startup" problem.
_MUTEX_NAME = "FridayTrayMutex_v1"
_mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
_last_error   = ctypes.windll.kernel32.GetLastError()
ERROR_ALREADY_EXISTS = 183

if _last_error == ERROR_ALREADY_EXISTS:
    # Another tray instance is already running — quit silently
    sys.exit(0)

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
friday_process = None
_icon_ref      = None


def _is_running() -> bool:
    return friday_process is not None and friday_process.poll() is None


# ── Icon drawing ──────────────────────────────────────────────────────────────
def _make_icon(running: bool) -> Image.Image:
    SIZE = 64
    img  = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d    = ImageDraw.Draw(img)
    bg   = (30, 180, 80) if running else (100, 100, 100)
    d.ellipse([4, 4, SIZE - 4, SIZE - 4], fill=bg, outline=(255, 255, 255), width=3)
    d.rounded_rectangle([24, 12, 40, 36], radius=7, fill=(255, 255, 255))
    d.arc([16, 26, 48, 46], start=0, end=180, fill=(255, 255, 255), width=3)
    d.rectangle([30, 46, 34, 54], fill=(255, 255, 255))
    d.rectangle([24, 53, 40, 57], fill=(255, 255, 255))
    return img


# ── Refresh tray ──────────────────────────────────────────────────────────────
def _refresh():
    if _icon_ref is None:
        return
    try:
        _icon_ref.icon  = _make_icon(_is_running())
        _icon_ref.title = "Friday  Running" if _is_running() else "Friday  Stopped"
        _icon_ref.update_menu()
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
    return "[Running]" if _is_running() else "[Stopped]"


# ── Open log ──────────────────────────────────────────────────────────────────
def open_log(icon=None, menu_item=None):
    target = LOG_FILE if LOG_FILE.exists() else ERR_LOG
    if target.exists():
        os.startfile(str(target))
    else:
        _log("open_log: no log file found yet")


# ── Watchdog ──────────────────────────────────────────────────────────────────
def _watchdog():
    global friday_process
    while True:
        time.sleep(4)
        if friday_process is not None and friday_process.poll() is not None:
            exit_code = friday_process.returncode
            _log(f"Friday process ended (exit code {exit_code})")
            friday_process = None
            _refresh()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _icon_ref

    _log("Tray app started")

    menu = pystray.Menu(
        item(_status_label,         None,         enabled=False),
        pystray.Menu.SEPARATOR,
        item("Start Friday",        start_friday),
        item("Stop Friday",         stop_friday),
        pystray.Menu.SEPARATOR,
        item("Open Log",            open_log),
        pystray.Menu.SEPARATOR,
        item("Quit Tray",           quit_tray),
    )

    _icon_ref = pystray.Icon(
        name  = "Friday",
        icon  = _make_icon(False),
        title = "Friday  Stopped",
        menu  = menu,
    )

    # Start watchdog thread
    threading.Thread(target=_watchdog, daemon=True).start()

    # Auto-start Friday after a delay, so heavy boot items (Docker Desktop,
    # OneDrive, Teams, audio drivers) finish their initial spike before
    # Whisper starts loading its model. Safe because the mutex above
    # guarantees only one tray ever runs.
    _AUTOSTART_DELAY = 30.0  # seconds
    _log(f"Auto-start scheduled in {_AUTOSTART_DELAY}s")
    threading.Timer(_AUTOSTART_DELAY, lambda: start_friday(_icon_ref)).start()

    _icon_ref.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log(f"FATAL tray error:\n{traceback.format_exc()}")
