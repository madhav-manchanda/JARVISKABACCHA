"""
api/routes/timers.py — Read-only timer endpoints.
In the web-only architecture, timers are not actively managed by the backend.
"""

from fastapi import APIRouter, Depends
from typing import Any

from auth import get_current_user

router = APIRouter(tags=["Timers"])


@router.get("/timers")
async def read_timers(username: str = Depends(get_current_user)) -> Any:
    """
    List active timers.
    NOTE: Timers are currently disabled in the web-only architecture.
    """
    return {
        "success": True, 
        "timers": [], 
        "message": "Timers are currently disabled."
    }
