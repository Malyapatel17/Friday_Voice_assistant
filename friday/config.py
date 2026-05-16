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
