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
