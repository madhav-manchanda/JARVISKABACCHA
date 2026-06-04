"""
voice.py — Speech-to-text (Whisper) and text-to-speech (pyttsx3 / ElevenLabs).
Whisper model is loaded exactly once at startup and kept in memory.
On headless VPS: audio is saved to file only — never played back.
ffmpeg is used to normalize uploaded audio to 16kHz mono WAV before Whisper.
"""

import logging
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from config import CONFIG

logger = logging.getLogger(__name__)

# ── Whisper singleton ──────────────────────────────────────────────────────────
_whisper_model = None
_whisper_lock = threading.Lock()
_whisper_loaded = False


def load_whisper() -> None:
    """
    Load the Whisper STT model into memory.
    Should be called once during application startup.
    Thread-safe — subsequent calls are no-ops.
    """
    global _whisper_model, _whisper_loaded
    with _whisper_lock:
        if _whisper_loaded:
            return
        try:
            import whisper  # type: ignore[import]
            logger.info("Loading Whisper model '%s' (this may take a moment)…", CONFIG.WHISPER_MODEL)
            _whisper_model = whisper.load_model(CONFIG.WHISPER_MODEL)
            _whisper_loaded = True
            logger.info("Whisper model '%s' loaded successfully.", CONFIG.WHISPER_MODEL)
        except ImportError:
            logger.warning("openai-whisper not installed — STT will be unavailable.")
        except Exception as exc:
            logger.error("Failed to load Whisper: %s", exc)


def is_whisper_loaded() -> bool:
    """Return True if the Whisper model has been loaded successfully."""
    return _whisper_loaded


# ── Audio normalisation ────────────────────────────────────────────────────────

def _normalize_audio(input_path: str) -> str:
    """
    Use ffmpeg to convert any audio format to 16kHz mono WAV.
    Whisper requires this format for best accuracy.

    Args:
        input_path: Path to the source audio file (WAV, MP3, M4A, OGG, WEBM, etc.).

    Returns:
        Path to the normalized WAV file (temporary — caller must delete).

    Raises:
        RuntimeError if ffmpeg fails or is not installed.
    """
    out_path = str(Path(CONFIG.AUDIO_CACHE_FOLDER) / f"norm_{uuid.uuid4().hex}.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "16000",          # 16kHz sample rate
        "-ac", "1",              # mono
        "-c:a", "pcm_s16le",     # PCM 16-bit little-endian
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg normalization failed: {result.stderr.decode(errors='replace')[:300]}"
        )
    return out_path


# ── Transcription ──────────────────────────────────────────────────────────────

def transcribe_file(audio_path: str) -> dict:
    """
    Transcribe an audio file to text using the local Whisper model.
    Automatically normalises the audio to 16kHz mono WAV first.

    Args:
        audio_path: Absolute path to the audio file.
                    Supported formats: WAV, MP3, M4A, OGG, WEBM, FLAC.

    Returns:
        Dict with keys:
          text (str)      — transcribed text
          language (str)  — detected language code (e.g. 'en', 'hi')
          confidence (float) — 0.0–1.0 (approximated from avg log-probability)
    """
    if not _whisper_loaded or _whisper_model is None:
        logger.error("Whisper not loaded — call load_whisper() first.")
        return {"text": "", "language": "en", "confidence": 0.0}

    normalized = None
    try:
        normalized = _normalize_audio(audio_path)
        with _whisper_lock:
            result = _whisper_model.transcribe(
                normalized,
                task="transcribe",
                fp16=False,
                verbose=False,
            )
        text = (result.get("text") or "").strip()
        language = result.get("language", "en")
        # Approximate confidence from segment log-probabilities
        segments = result.get("segments", [])
        if segments:
            avg_logprob = sum(s.get("avg_logprob", -1.0) for s in segments) / len(segments)
            confidence = round(min(1.0, max(0.0, 1.0 + avg_logprob)), 3)
        else:
            confidence = 1.0 if text else 0.0

        logger.info("STT [%s | %.2f]: %s", language, confidence, text[:80])
        return {"text": text, "language": language, "confidence": confidence}

    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        return {"text": "", "language": "en", "confidence": 0.0}
    finally:
        if normalized:
            try:
                Path(normalized).unlink(missing_ok=True)
            except Exception:
                pass


def transcribe_bytes(audio_bytes: bytes, suffix: str = ".wav") -> dict:
    """
    Transcribe audio from raw bytes (used for API upload path).
    Writes bytes to a temp file, transcribes, then deletes the temp file.

    Args:
        audio_bytes: Raw audio content from an HTTP multipart upload.
        suffix: File extension indicating format (e.g. '.wav', '.m4a', '.ogg').

    Returns:
        Same dict shape as transcribe_file.
    """
    tmp = Path(CONFIG.AUDIO_CACHE_FOLDER) / f"upload_{uuid.uuid4().hex}{suffix}"
    try:
        tmp.write_bytes(audio_bytes)
        return transcribe_file(str(tmp))
    except Exception as exc:
        logger.error("transcribe_bytes failed: %s", exc)
        return {"text": "", "language": "en", "confidence": 0.0}
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def detect_silence(audio_path: str) -> bool:
    """
    Detect if an audio file is mostly silence using ffmpeg's silencedetect filter.
    Useful for VAD validation on uploaded audio before running Whisper.

    Args:
        audio_path: Path to the audio file to analyse.

    Returns:
        True if the audio appears to be mostly silent (< 0.5 s of sound).
    """
    try:
        cmd = [
            "ffmpeg", "-i", audio_path,
            "-af", "silencedetect=noise=-40dB:d=0.5",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        stderr = result.stderr.decode(errors="replace")
        # If no silence_end found, the whole file is silent
        return "silence_end" not in stderr
    except Exception:
        return False


# ── Text-to-speech ─────────────────────────────────────────────────────────────

def speak(text: str, language: str = "en") -> Optional[str]:
    """
    Convert text to speech and save to a file in audio_cache/.
    On headless VPS: file is saved only — no playback attempted.
    Chooses ElevenLabs (if configured) or pyttsx3 (offline fallback).

    Args:
        text: The text to synthesise. Empty strings return None.
        language: Detected language code — used to select voice if applicable.

    Returns:
        Absolute path to the generated audio file, or None on failure.
    """
    if not text or not text.strip():
        return None

    if CONFIG.has_elevenlabs():
        return _speak_elevenlabs(text)
    return _speak_pyttsx3(text)


def _speak_pyttsx3(text: str) -> Optional[str]:
    """
    Generate speech with pyttsx3 (offline, cross-platform).

    Args:
        text: The text to synthesise.

    Returns:
        Path to the saved WAV file, or None on failure.
    """
    try:
        import pyttsx3  # type: ignore[import]
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 0.9)
        out = Path(CONFIG.AUDIO_CACHE_FOLDER) / f"tts_{uuid.uuid4().hex}.wav"
        engine.save_to_file(text, str(out))
        engine.runAndWait()
        logger.debug("TTS (pyttsx3) → %s", out.name)
        return str(out)
    except ImportError:
        logger.warning("pyttsx3 not installed — TTS unavailable.")
        return None
    except Exception as exc:
        logger.error("pyttsx3 TTS failed: %s", exc)
        return None


def _speak_elevenlabs(text: str) -> Optional[str]:
    """
    Generate speech with the ElevenLabs API (online, high quality).

    Args:
        text: The text to synthesise.

    Returns:
        Path to the saved MP3 file, or None on failure.
    """
    try:
        import requests as req  # type: ignore[import]
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{CONFIG.ELEVENLABS_VOICE_ID}"
        headers = {
            "Accept": "audio/mpeg",
            "xi-api-key": CONFIG.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        resp = req.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        out = Path(CONFIG.AUDIO_CACHE_FOLDER) / f"tts_{uuid.uuid4().hex}.mp3"
        out.write_bytes(resp.content)
        logger.debug("TTS (ElevenLabs) → %s", out.name)
        return str(out)
    except Exception as exc:
        logger.error("ElevenLabs TTS failed: %s — falling back to pyttsx3.", exc)
        return _speak_pyttsx3(text)


def cleanup_audio_cache(max_age_seconds: int = 300) -> int:
    """
    Delete audio cache files older than max_age_seconds.
    Should be called by a background scheduler periodically.

    Args:
        max_age_seconds: Files older than this are deleted (default 5 min).

    Returns:
        Number of files deleted.
    """
    cache_dir = Path(CONFIG.AUDIO_CACHE_FOLDER)
    now = time.time()
    deleted = 0
    for f in cache_dir.glob("tts_*"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
                deleted += 1
        except Exception:
            pass
    if deleted:
        logger.debug("Audio cache cleanup: deleted %d files.", deleted)
    return deleted
