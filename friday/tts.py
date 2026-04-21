"""
friday/tts.py — Text-to-Speech
  Online  → edge-tts Jenny Neural voice (played via pygame)
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


def _play_mp3(path):
    """
    Play an MP3 file silently through the default speaker.
    Uses pygame (no dialogs, no popups, works from tray/BAT context).
    Falls back to pydub if pygame is missing.
    """
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        return
    except ImportError:
        pass  # pygame not installed, try pydub

    try:
        from pydub import AudioSegment
        from pydub.playback import play
        audio = AudioSegment.from_mp3(path)
        play(audio)
        return
    except ImportError:
        pass  # pydub not installed either

    # Last resort: PowerShell MediaPlayer (no dialog, but timing is approximate)
    import subprocess, time
    escaped = path.replace("\\", "\\\\")
    subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-c",
            f'Add-Type -AssemblyName PresentationCore;'
            f'$p=[System.Windows.Media.MediaPlayer]::new();'
            f'$p.Open([uri]"{escaped}");'
            f'$p.Play();'
            f'Start-Sleep -Seconds 5'
        ],
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=10
    )


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
        _play_mp3(tmp_path)

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