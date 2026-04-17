# ─────────────────────────────────────────────
#  Friday — Central Configuration
# ─────────────────────────────────────────────

# Wake word
WAKE_WORD = "friday"

# Vosk model folder (relative to main.py)
MODEL_PATH = "model"

# ── Timeouts ──────────────────────────────────
ACTIVE_DURATION = 10          # seconds to wait for a command after wake word
CHAT_TIMEOUT = 30             # seconds of inactivity before exiting chat mode

# ── TTS ───────────────────────────────────────
TTS_RATE = 180                # pyttsx3 offline speech rate (words per minute)
EDGE_VOICE = "en-US-JennyNeural"  # Online voice (edge-tts)
# Other free female voices: en-US-AriaNeural, en-GB-SoniaNeural, en-IN-NeerjaNeural

# ── Groq AI (Conversational mode) ─────────────
# Get your FREE API key at: https://console.groq.com
import os
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Free-tier model options:
#   "llama-3.3-70b-versatile"   — best quality,  30 req/min
#   "llama3-8b-8192"            — fastest,        30 req/min
#   "mixtral-8x7b-32768"        — balanced,       30 req/min
GROQ_MODEL = "llama-3.3-70b-versatile"
