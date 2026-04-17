"""
friday/tts.py — Text-to-Speech
  Online  → edge-tts Jenny Neural voice
  Offline → pyttsx3 Microsoft Zira
"""

import asyncio
import os
import tempfile

import pyttsx3


def discover_offline_voice_id():
    """Find female pyttsx3 voice ID at startup. Returns None if unavailable."""
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        selected = None
        for voice in voices:
            if 'zira' in voice.name.lower() or 'female' in voice.name.lower():
                selected = voice.id
                break
        if not selected and voices:
            selected = voices[0].id
        engine.stop()
        return selected
    except Exception as e:
        print(f"⚠️  Could not discover offline voice: {e}")
        return None


def speak(text, audio_stream=None, is_online=False, offline_voice_id=None, tts_rate=180):
    """Speak text. Uses Jenny (online) or Zira (offline)."""
    print(f"🗣️  Friday: {text}")
    if is_online:
        _speak_online(text, audio_stream, offline_voice_id, tts_rate)
    else:
        _speak_offline(text, audio_stream, offline_voice_id, tts_rate)


def _speak_online(text, audio_stream, offline_voice_id, tts_rate):
    """Speak using edge-tts (Jenny Neural). Falls back to offline on error."""
    tmp_path = None
    try:
        import edge_tts
        from friday.config import EDGE_VOICE

        if audio_stream:
            audio_stream.stop_stream()

        async def _generate():
            communicate = edge_tts.Communicate(text, EDGE_VOICE)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                path = f.name
            await communicate.save(path)
            return path

        tmp_path = asyncio.run(_generate())

        try:
            from playsound import playsound
            playsound(tmp_path)
        except Exception:
            # Fallback: open with default player
            os.startfile(tmp_path)
            import time; time.sleep(3)

    except Exception as e:
        print(f"⚠️  Online TTS error: {e} — falling back to offline voice")
        _speak_offline(text, audio_stream, offline_voice_id, tts_rate)
        return  # stream already restarted in offline fallback
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if audio_stream:
            audio_stream.start_stream()


def _speak_offline(text, audio_stream, voice_id, rate):
    """Speak using pyttsx3 (Zira). Fresh engine each call to avoid state bugs."""
    try:
        if audio_stream:
            audio_stream.stop_stream()
        engine = pyttsx3.init()
        if voice_id:
            engine.setProperty('voice', voice_id)
        engine.setProperty('rate', rate)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"⚠️  Offline TTS error: {e}")
    finally:
        if audio_stream:
            audio_stream.start_stream()
