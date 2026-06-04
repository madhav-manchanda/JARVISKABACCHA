"""
api/routes/timers.py — Read-only timer endpoints.
In the new architecture, timers run on the Android device (via intents).
These endpoints are placeholders or can be used if we ever implement server-side timers again.
"""

from fastapi import APIRouter, Depends
from typing import Any

from auth import get_current_user

router = APIRouter(tags=["Timers"])


@router.get("/timers")
async def read_timers(username: str = Depends(get_current_user)) -> Any:
    """
    List active timers.
    NOTE: Timers are now handled by the Android app. This endpoint returns empty.
    """
    return {
        "success": True, 
        "timers": [], 
        "message": "Timers are handled on-device by the Android app."
    }
