"""
friday/launcher.py -- App launching, browser closing, shutdown dialog
"""

import os
import subprocess
import time
from pathlib import Path

from friday import config as cfg

CHROME_PATH = cfg.CHROME_PATH
ACCOUNT_WORK     = cfg.CHROME_WORK_PROFILE      # malya.patel@bytestechnolab.com
ACCOUNT_PERSONAL = cfg.CHROME_PERSONAL_PROFILE  # malyapatel17@gmail.com


def _verify_profiles() -> None:
    """Warn (do not crash) if either configured Chrome profile dir is missing."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return  # not Windows or unusual environment; skip silently
    user_data = Path(local) / "Google" / "Chrome" / "User Data"
    for profile in (ACCOUNT_WORK, ACCOUNT_PERSONAL):
        if not (user_data / profile).is_dir():
            print(
                f"[WARN] Chrome profile '{profile}' not found at "
                f"{user_data / profile} -- work mode tabs will open unauthenticated"
            )


_verify_profiles()


def open_profile(profile, url):
    subprocess.Popen([
        CHROME_PATH,
        f'--profile-directory={profile}',
        url
    ])


def _open_url(url, os_type):
    if os_type == "Darwin":
        subprocess.Popen(["open", url])
    elif os_type == "Windows":
        subprocess.Popen(["start", url], shell=True)
    elif os_type == "Linux":
        subprocess.Popen(["xdg-open", url])


def _launch_vscode(os_type):
    if os_type == "Darwin":
        subprocess.Popen(["open", "-a", "Visual Studio Code"])
    elif os_type == "Windows":
        subprocess.Popen(["start", "code"], shell=True)
    elif os_type == "Linux":
        subprocess.Popen(["code"])


def launch_work_apps(os_type):
    """Open Gmail (bytes account), Claude.ai + ChatGPT (personal account), VS Code."""
    print("\n[WORK MODE] Launching apps...\n")

    open_profile(ACCOUNT_WORK, "https://mail.google.com")  # bytes work mail
    print("  [OK] Opened Gmail (bytes)")
    time.sleep(0.5)

    open_profile(ACCOUNT_PERSONAL, "https://claude.ai")  # personal account
    print("  [OK] Opened Claude.ai (personal)")
    time.sleep(0.5)

    open_profile(ACCOUNT_PERSONAL, "https://chatgpt.com")  # personal account
    print("  [OK] Opened ChatGPT (personal)")
    time.sleep(0.5)

    _launch_vscode(os_type)
    print("  [OK] Launched VS Code\n")


def launch_entertainment_apps(os_type):
    """Open YouTube, Hotstar and Amazon Prime."""
    print("\n[ENTERTAINMENT MODE] Launching apps...\n")

    _open_url("https://youtube.com", os_type)
    print("  [OK] Opened YouTube")
    time.sleep(0.5)

    _open_url("https://hotstar.com", os_type)
    print("  [OK] Opened Hotstar")
    time.sleep(0.5)

    _open_url("https://primevideo.com", os_type)
    print("  [OK] Opened Amazon Prime\n")


def close_browsers(os_type):
    """Force-close all major browsers."""
    print("[INFO] Closing all browsers...")
    if os_type == "Windows":
        for exe in ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"]:
            subprocess.run(["taskkill", "/f", "/im", exe],
                           capture_output=True, shell=True)
    elif os_type == "Darwin":
        for app in ["Google Chrome", "Safari", "Firefox", "Opera"]:
            subprocess.run(["osascript", "-e", f'quit app "{app}"'],
                           capture_output=True)
    elif os_type == "Linux":
        for proc in ["chrome", "chromium", "firefox", "opera"]:
            subprocess.run(["pkill", "-f", proc], capture_output=True)
    print("[OK] Browsers closed")


def open_shutdown_dialog(os_type):
    """Open the OS shutdown/power-off dialog."""
    print("[INFO] Opening shutdown dialog...")
    if os_type == "Windows":
        subprocess.Popen(
            ["powershell", "-Command",
             "(New-Object -ComObject Shell.Application).ShutdownWindows()"]
        )
    elif os_type == "Darwin":
        subprocess.Popen(
            ["osascript", "-e",
             'tell application "System Events" to shut down']
        )
    elif os_type == "Linux":
        subprocess.Popen(["gnome-session-quit", "--power-off"])