"""
brain.py — The AI core of Jarvis.
Uses Claude API (claude-sonnet-4-20250514) to classify every user command
into a structured intent following the exact Android integration contract.

Key design: the response always includes `execution_target`:
  "server"  → VPS already executed the action
  "device"  → Android app will execute it on-device via AccessibilityService

Session history is kept in Redis (fast) and persisted to SQLite.
All API calls retry 3× with exponential backoff.
"""

import json
import logging
import time
from typing import Any, Optional

import anthropic

from config import CONFIG
from memory import (
    save_message,
    get_cached_history,
    cache_session_history,
    log_intent,
)
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Jarvis, a personal AI assistant for Madhav.

You understand Hindi, English, Hinglish, Tamil, Telugu, Bengali, Marathi, Punjabi, Urdu, Kannada, Malayalam, and mixed-language input.

CRITICAL: Always respond with ONLY a single valid JSON object. No markdown, no prose, no backticks, no explanations outside the JSON.

══════════════════════════════════════════════
RESPONSE CONTRACT — always return this exact shape:
══════════════════════════════════════════════
{
  "action": "<action_name>",
  "execution_target": "server" | "device",
  "params": { ...action-specific params... },
  "response_text": "<natural language reply in user's language>",
  "language": "<detected language: en|hi|hi-en|ta|te|bn|mr|pa|ur|kn|ml>",
  "confidence": <float 0.0–1.0>,
  "confirmation_required": false,
  "confirmation_message": null,
  "app": null
}

══════════════════════════════════════════════
SERVER-SIDE ACTIONS (VPS executes — execution_target: "server"):
══════════════════════════════════════════════
google_search    params: {query: str, num_results: int=5}
google_dork      params: {user_intent: str}
download_file    params: {url: str}
download_video   params: {url: str}
get_weather      params: {city: str}
remember_fact    params: {key: str, value: str}
recall_fact      params: {key: str}
list_facts       params: {}
system_info      params: {}
general_chat     params: {}
clarify          params: {question: str}

══════════════════════════════════════════════
DEVICE-SIDE ACTIONS (Android app executes — execution_target: "device"):
══════════════════════════════════════════════
send_whatsapp    app: "whatsapp"    params: {contact: str, message: str, phone?: str}
make_call        app: "dialer"      params: {contact: str, phone_number?: str}
send_sms         app: "messages"    params: {contact: str, phone_number?: str, message: str}
set_timer        app: "clock"       params: {duration_seconds: int, label: str}
set_alarm        app: "clock"       params: {time_24h: str, label: str, days?: [str]}
upi_payment      app: "gpay"        params: {contact: str, upi_id?: str, amount: int, note?: str}
open_app         app: "<pkg_name>"  params: {app_name: str}
take_screenshot  app: "system"      params: {}
set_volume       app: "system"      params: {level: int, type: str}

══════════════════════════════════════════════
RULES:
══════════════════════════════════════════════

1. LANGUAGE: Detect the user's language. Set "language" field. Write response_text in THAT same language. For Hinglish input → Hinglish response.

2. CONFIRMATION: For these actions ALWAYS set confirmation_required: true and write confirmation_message in user's language:
   - upi_payment (always)
   - send_whatsapp (always)
   - make_call (always)
   - send_sms (always)

3. CONTACTS/UPI: Never guess a phone number or UPI ID. If you don't know it:
   - First try: action = recall_fact, params: {key: "<name>_upi"} or {key: "<name>_phone"}
   - If still unknown: ask user via action = clarify

4. TIME PARSING (Indian context):
   - "kal subah 8 baje" → time_24h: "08:00", set_alarm with days: ["tomorrow"]
   - "2 ghante baad" → set_timer with duration_seconds: 7200
   - "aaj raat 10 baje" → time_24h: "22:00"
   - "abhi" → immediately (duration_seconds: 0 means execute now)
   - "parso" → day after tomorrow

5. AMBIGUITY: If the intent is unclear, use action: "clarify" and ask exactly ONE focused question.

6. ERRORS: If a feature is unavailable (no API key), set action: "general_chat" and explain politely.

7. PAYMENTS: For UPI payment, identify which app to use from context (GPay/PhonePe/Paytm). Default to "gpay".

8. JSON ONLY: Your entire response must be parseable by json.loads(). Nothing else.
"""

# ── Actions that execute on device (Android app handles these) ─────────────────
DEVICE_ACTIONS = {
    "send_whatsapp", "make_call", "send_sms", "set_timer", "set_alarm",
    "upi_payment", "open_app", "take_screenshot", "set_volume",
}

# ── Actions that require confirmation ─────────────────────────────────────────
CONFIRMATION_REQUIRED_ACTIONS = {
    "upi_payment", "send_whatsapp", "make_call", "send_sms",
}


def _call_claude(messages: list[dict]) -> str:
    """
    Make a single Claude API call with the given message history.

    Args:
        messages: List of dicts with 'role' and 'content' keys.

    Returns:
        Raw text content from Claude's response.

    Raises:
        anthropic.APIError on API failure (caller should retry).
    """
    client = anthropic.Anthropic(api_key=CONFIG.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=CONFIG.CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


def _parse_response(raw: str, language: str = "en") -> dict:
    """
    Parse and validate Claude's JSON response.
    Strips any accidental markdown fences.
    Returns a safe fallback on parse failure.

    Args:
        raw: The raw string from Claude.
        language: Fallback language if parsing fails.

    Returns:
        Validated intent dict matching the Android contract.
    """
    text = raw.strip()
    # Strip any accidental code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Brain JSON parse error (%s): %.200s", exc, raw)
        return {
            "action": "general_chat",
            "execution_target": "server",
            "params": {},
            "response_text": raw,
            "language": language,
            "confidence": 0.5,
            "confirmation_required": False,
            "confirmation_message": None,
            "app": None,
        }

    # Normalise and fill defaults
    action = data.get("action", "general_chat")
    data.setdefault("action", action)
    data.setdefault("execution_target", "device" if action in DEVICE_ACTIONS else "server")
    data.setdefault("params", {})
    data.setdefault("response_text", "")
    data.setdefault("language", language)
    data.setdefault("confidence", 1.0)
    data.setdefault("app", None)

    # Force confirmation flags for sensitive actions
    if action in CONFIRMATION_REQUIRED_ACTIONS:
        data["confirmation_required"] = True
    else:
        data.setdefault("confirmation_required", False)
    data.setdefault("confirmation_message", None)

    return data


async def process(
    text: str,
    session_id: str,
    language_hint: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process a user text command through the Claude brain.

    Steps:
      1. Load session history from Redis (or SQLite fallback).
      2. Append the new user turn.
      3. Call Claude API with retry + exponential backoff.
      4. Parse the structured intent response.
      5. Persist both turns to Redis + SQLite.
      6. Log the intent to intent_log table.
      7. Return the full intent dict.

    Args:
        text: User's input (any supported language, already transcribed if from voice).
        session_id: Unique identifier for this conversation session.
        language_hint: Optional language code from Whisper (e.g. 'hi').

    Returns:
        Full intent dict matching the Android integration contract.
    """
    # Sanitise input
    text = text.strip()[: CONFIG.MAX_INPUT_LENGTH]
    if not text:
        return _empty_response(session_id, language_hint or "en")

    # Load session history
    history = get_cached_history(session_id) or []

    # Build Claude messages (keep last N*2 turns)
    max_turns = CONFIG.SESSION_HISTORY_LENGTH * 2
    claude_msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-max_turns:]
        if m.get("role") in ("user", "assistant")
    ]
    claude_msgs.append({"role": "user", "content": text})

    # Call Claude with retry
    start = time.time()
    try:
        def _api_call() -> str:
            return _call_claude(claude_msgs)

        raw = retry_with_backoff(_api_call, max_retries=3, base_delay=1.0)
    except Exception as exc:
        logger.error("Claude API failed after retries (session=%s): %s", session_id[:8], exc)
        return _error_response(session_id, language_hint or "en")

    latency_ms = int((time.time() - start) * 1000)
    parsed = _parse_response(raw, language_hint or "en")

    logger.info(
        "Brain [session=%s | %dms] action=%s target=%s lang=%s conf=%.2f",
        session_id[:8],
        latency_ms,
        parsed.get("action"),
        parsed.get("execution_target"),
        parsed.get("language"),
        parsed.get("confidence", 1.0),
    )

    # Persist history
    assistant_summary = parsed.get("response_text", raw)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": assistant_summary, "action": parsed.get("action")})
    cache_session_history(session_id, history)

    # Async SQLite persistence
    await save_message(
        session_id, "user", text,
        language=parsed.get("language", "en"),
    )
    await save_message(
        session_id, "assistant", assistant_summary,
        language=parsed.get("language", "en"),
        action=parsed.get("action"),
    )

    # Intent audit log
    await log_intent(
        session_id=session_id,
        action=parsed.get("action", "unknown"),
        execution_target=parsed.get("execution_target", "server"),
        params=parsed.get("params"),
        success=True,
    )

    return parsed


def _empty_response(session_id: str, language: str) -> dict:
    """Return a friendly empty-input response."""
    msg = "Haan bolo?" if language.startswith("hi") else "Yes, I'm listening. Go ahead!"
    return {
        "action": "general_chat",
        "execution_target": "server",
        "params": {},
        "response_text": msg,
        "language": language,
        "confidence": 1.0,
        "confirmation_required": False,
        "confirmation_message": None,
        "app": None,
    }


def _error_response(session_id: str, language: str) -> dict:
    """Return a graceful error response when Claude API is unavailable."""
    msg = (
        "Mera brain abhi thoda busy hai. Thodi der baad try karein."
        if language.startswith("hi")
        else "My brain is temporarily unavailable. Please try again in a moment."
    )
    return {
        "action": "general_chat",
        "execution_target": "server",
        "params": {},
        "response_text": msg,
        "language": language,
        "confidence": 0.0,
        "confirmation_required": False,
        "confirmation_message": None,
        "app": None,
    }


def clear_session(session_id: str) -> None:
    """
    Clear a session's conversation history from Redis.

    Args:
        session_id: Session to clear.
    """
    from memory import _get_redis, _rkey_history
    r = _get_redis()
    if r:
        try:
            r.delete(_rkey_history(session_id))
        except Exception:
            pass
