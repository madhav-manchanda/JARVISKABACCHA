"""
api/routes/health.py — Public health check endpoint.
No authentication required.
"""

from fastapi import APIRouter
from typing import Any
import time

from config import CONFIG
from voice import is_whisper_loaded

router = APIRouter(tags=["Health"])

_START_TIME = time.time()


@router.get("/health")
async def health_check() -> Any:
    """
    Public health check endpoint.
    Returns status of various subsystems.
    """
    uptime = int(time.time() - _START_TIME)
    
    from memory import _redis
    
    return {
        "status": "ok",
        "version": CONFIG.VERSION,
        "uptime_seconds": uptime,
        "whisper_loaded": is_whisper_loaded(),
        "redis_connected": _redis is not None,
        "features": {
            "search": CONFIG.has_serpapi(),
            "tts_elevenlabs": CONFIG.has_elevenlabs(),
            "tts_local": CONFIG.TTS_ENGINE == "pyttsx3",
        }
    }
