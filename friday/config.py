# ─────────────────────────────────────────────
#  Friday — Phase 1 Configuration
# ─────────────────────────────────────────────

# Wake word (lowercase)
WAKE_WORD = "friday"

# Vosk SMALL model folder (relative to main.py)
# Download: https://alphacephei.com/vosk/models  →  vosk-model-small-en-us-0.15
# Extract and rename the folder to "model" next to main.py
MODEL_PATH = "model"

# Seconds to wait for a command after the wake word is heard
ACTIVE_DURATION = 30

# Offline TTS speech rate (words per minute)
TTS_RATE = 180

# ─────────────────────────────────────────────
# Chrome profile mapping (work mode)
# ─────────────────────────────────────────────
# Resolve profile dirs with:
#   Get-ChildItem "$env:LOCALAPPDATA\Google\Chrome\User Data" -Directory
# Pick the directory whose Preferences file contains the email you want.
CHROME_PATH             = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_WORK_PROFILE     = "Profile 5"  # malya.patel@bytestechnolab.com
CHROME_PERSONAL_PROFILE = "Default"    # malyapatel17@gmail.com

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

# ─────────────────────────────────────────────
# Ask mode (GroqChat)
# ─────────────────────────────────────────────
import os as _os
GROQ_MODEL = _os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
