"""
actions/timer.py — Timer and alarm management for Jarvis.
Uses threading.Timer for execution, dateparser for multilingual time parsing,
and pushes WebSocket events when timers fire.
All timers are persisted in SQLite so they survive process restarts.
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import dateparser

from memory import save_timer, update_timer_status, list_active_timers, get_timer

logger = logging.getLogger(__name__)

# ── Active timer registry — maps timer_id → threading.Timer ──────────────────
_active_timers: dict[int, threading.Timer] = {}
_timers_lock = threading.Lock()

# ── WebSocket push callback (set by server.py on startup) ─────────────────────
_ws_push_callback: Optional[Callable] = None


def set_ws_callback(callback: Callable) -> None:
    """
    Register a callback for pushing WebSocket events when timers fire.
    The callback signature: callback(session_id: str, event: dict) -> None

    Args:
        callback: Async or sync function that sends a WS event.
    """
    global _ws_push_callback
    _ws_push_callback = callback


def _push_event(session_id: Optional[str], event: dict) -> None:
    """
    Push a WebSocket event to the associated session, if available.

    Args:
        session_id: The session to notify.
        event: The event dict to send.
    """
    if _ws_push_callback and session_id:
        try:
            if asyncio.iscoroutinefunction(_ws_push_callback):
                loop = asyncio.new_event_loop()
                loop.run_until_complete(_ws_push_callback(session_id, event))
                loop.close()
            else:
                _ws_push_callback(session_id, event)
        except Exception as exc:
            logger.warning("WebSocket push failed: %s", exc)


# ── Timer duration parsing ────────────────────────────────────────────────────

def parse_duration(duration_input: Any) -> Optional[int]:
    """
    Parse a duration into seconds from various formats.
    Accepts:
      - int/float (already seconds)
      - "5 minutes", "2 ghante", "half an hour", "30 seconds"
      - Negative or zero values are rejected.

    Args:
        duration_input: Raw duration value from brain params.

    Returns:
        Duration in seconds as an integer, or None if unparseable.
    """
    if isinstance(duration_input, (int, float)):
        return int(duration_input) if duration_input > 0 else None

    text = str(duration_input).strip()

    # Map common Hindi time words
    hindi_map = {
        "ghante": "hours",
        "ghanta": "hour",
        "minute": "minute",
        "min": "minute",
        "second": "second",
        "sec": "second",
        "din": "days",
        "din baad": "days later",
        "half an hour": "30 minutes",
        "aadha ghanta": "30 minutes",
    }
    text_lower = text.lower()
    for hindi, english in hindi_map.items():
        text_lower = text_lower.replace(hindi, english)

    # Try dateparser relative parsing
    now = datetime.now(timezone.utc)
    settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now,
        "LANGUAGES": ["en", "hi"],
    }
    parsed_dt = dateparser.parse(f"in {text_lower}", settings=settings)
    if parsed_dt:
        delta = (parsed_dt - now).total_seconds()
        if delta > 0:
            return int(delta)

    # Try pure numeric extraction as fallback
    import re
    match = re.search(r"(\d+(?:\.\d+)?)\s*(hour|hr|minute|min|second|sec)?", text_lower)
    if match:
        val = float(match.group(1))
        unit = (match.group(2) or "sec").lower()
        if "hour" in unit or unit == "hr":
            return int(val * 3600)
        elif "min" in unit:
            return int(val * 60)
        else:
            return int(val)

    logger.warning("Could not parse duration: %s", duration_input)
    return None


def parse_alarm_time(time_str: str) -> Optional[datetime]:
    """
    Parse an alarm time string into a future UTC datetime.
    Handles: "7am", "kal subah 7 baje", "tomorrow 8:30am", "2025-06-15 09:00".

    Args:
        time_str: Natural language or ISO datetime string.

    Returns:
        Future UTC datetime, or None if unparseable.
    """
    settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "LANGUAGES": ["en", "hi"],
    }
    # Map Hindi time words
    normalized = (
        time_str
        .replace("kal subah", "tomorrow morning")
        .replace("kal raat", "tomorrow night")
        .replace("aaj subah", "this morning")
        .replace("aaj raat", "tonight")
        .replace("baje", "o'clock")
    )
    dt = dateparser.parse(normalized, settings=settings)
    if dt:
        now = datetime.now(timezone.utc)
        if dt <= now:
            dt += timedelta(days=1)  # If parsed time is in the past, add one day
        return dt
    return None


# ── Core timer logic ──────────────────────────────────────────────────────────

async def set_timer(
    duration_seconds: Any,
    label: str = "Timer",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create and start a countdown timer.

    Args:
        duration_seconds: Duration (int seconds or natural language string).
        label: Human-readable label for this timer.
        session_id: Session to notify when the timer fires.

    Returns:
        Dict with keys: success, timer_id, label, duration_seconds, fires_at.
    """
    secs = parse_duration(duration_seconds)
    if secs is None or secs <= 0:
        return {
            "success": False,
            "error": f"Could not parse duration: {duration_seconds}",
        }

    fire_at = datetime.now(timezone.utc) + timedelta(seconds=secs)
    timer_id = await save_timer(label, fire_at, secs, session_id)

    def _on_fire():
        logger.info("Timer fired: [%d] %s", timer_id, label)
        # Update DB
        loop = asyncio.new_event_loop()
        loop.run_until_complete(update_timer_status(timer_id, "fired"))
        loop.close()

        # WebSocket push
        _push_event(
            session_id,
            {
                "event": "timer_fired",
                "data": {"timer_id": timer_id, "label": label},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Remove from active registry
        with _timers_lock:
            _active_timers.pop(timer_id, None)

    t = threading.Timer(secs, _on_fire)
    t.daemon = True
    t.start()

    with _timers_lock:
        _active_timers[timer_id] = t

    logger.info("Timer set: id=%d label=%s duration=%ds", timer_id, label, secs)
    return {
        "success": True,
        "timer_id": timer_id,
        "label": label,
        "duration_seconds": secs,
        "fires_at": fire_at.isoformat(),
    }


async def set_alarm(
    time_str: str,
    label: str = "Alarm",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create an alarm that fires at a specific future time.

    Args:
        time_str: Natural language time string (e.g. 'kal subah 7 baje').
        label: Human-readable label.
        session_id: Session to notify when alarm fires.

    Returns:
        Same shape as set_timer return value.
    """
    fire_at = parse_alarm_time(time_str)
    if not fire_at:
        return {
            "success": False,
            "error": f"Could not parse alarm time: {time_str}",
        }

    now = datetime.now(timezone.utc)
    secs = int((fire_at - now).total_seconds())
    return await set_timer(secs, label, session_id)


async def cancel_timer(
    label: Optional[str] = None,
    timer_id: Optional[int] = None,
) -> dict[str, Any]:
    """
    Cancel an active timer by label or ID.

    Args:
        label: Timer label to search for (partial match).
        timer_id: Exact timer ID to cancel.

    Returns:
        Dict with keys: success, cancelled (list of cancelled timer IDs).
    """
    cancelled = []

    if timer_id is not None:
        with _timers_lock:
            t = _active_timers.pop(timer_id, None)
        if t:
            t.cancel()
            await update_timer_status(timer_id, "cancelled")
            cancelled.append(timer_id)
    elif label:
        timers = await list_active_timers()
        label_lower = label.lower()
        for tmr in timers:
            if label_lower in tmr["label"].lower():
                tid = tmr["id"]
                with _timers_lock:
                    t = _active_timers.pop(tid, None)
                if t:
                    t.cancel()
                await update_timer_status(tid, "cancelled")
                cancelled.append(tid)

    if cancelled:
        return {"success": True, "cancelled": cancelled}
    return {"success": False, "error": "No matching timer found."}


async def get_timers() -> dict[str, Any]:
    """
    List all active timers.

    Returns:
        Dict with key 'timers' containing a list of active timer dicts.
    """
    timers = await list_active_timers()
    now = datetime.now(timezone.utc)
    result = []
    for tmr in timers:
        try:
            fire_at = datetime.fromisoformat(tmr["fire_at"])
            remaining = max(0, int((fire_at - now).total_seconds()))
        except Exception:
            remaining = 0
        result.append({**tmr, "remaining_seconds": remaining})
    return {"success": True, "timers": result}
