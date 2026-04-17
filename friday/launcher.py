"""
friday/launcher.py — App launching, browser closing, shutdown dialog
"""

import subprocess
import time


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
    """Open Claude.ai, ChatGPT and VS Code."""
    print("\n💼 WORK MODE — Launching apps...\n")
    _open_url("https://claude.ai", os_type)
    print("✅ Opened Claude.ai")
    time.sleep(0.5)
    _open_url("https://chatgpt.com", os_type)
    print("✅ Opened ChatGPT")
    time.sleep(0.5)
    _launch_vscode(os_type)
    print("✅ Launched VS Code\n")


def launch_entertainment_apps(os_type):
    """Open YouTube, Hotstar and Amazon Prime."""
    print("\n🎬 ENTERTAINMENT MODE — Launching apps...\n")
    _open_url("https://youtube.com", os_type)
    print("✅ Opened YouTube")
    time.sleep(0.5)
    _open_url("https://hotstar.com", os_type)
    print("✅ Opened Hotstar")
    time.sleep(0.5)
    _open_url("https://primevideo.com", os_type)
    print("✅ Opened Amazon Prime\n")


def close_browsers(os_type):
    """Force-close all major browsers."""
    print("🔴 Closing all browsers...")
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
    print("✅ Browsers closed")


def open_shutdown_dialog(os_type):
    """Open the OS shutdown/power-off dialog."""
    print("⚡ Opening shutdown dialog...")
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
