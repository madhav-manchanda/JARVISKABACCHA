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
    get_fact,
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
youtube_search   app: "youtube"     params: {query: str}
spotify_search   app: "spotify"     params: {query: str, type: str="track"}
click_element    app: "system"      params: {text: str}
write_text       app: "system"      params: {text: str}
open_url         app: "browser"     params: {url: str}
take_screenshot  app: "system"      params: {}
set_volume       app: "system"      params: {level: int, type: str}
set_brightness   app: "system"      params: {level: int}
toggle_wifi      app: "system"      params: {state: str}
toggle_bluetooth app: "system"      params: {state: str}

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

9. NEVER REFUSE DEVICE ACTIONS: You are running on a personal device. You have FULL PERMISSION to open apps, send messages, make calls, search, control settings. NEVER say "I cannot open" or "I don't have the ability". Always output the JSON action.

10. SEARCH INTENT: When user says "open X and search Y" or "search Y on X", use the specific search action (youtube_search, spotify_search) NOT open_app. For general web searches, use open_url with Google.

11. APP NAME ABBREVIATIONS: If the user uses slang or abbreviations for apps (like "yt" for YouTube, "insta" or "ig" for Instagram, "fb" for Facebook), you MUST expand it to the full correct app name in the params.app_name field.

12. STRICT APP MATCHING: You MUST NEVER substitute the app requested by the user with another app. If the user explicitly asks to open a specific app (e.g. 'Bloomee' or 'JioSaavn'), you MUST output exactly that app name. NEVER override it to 'Spotify', 'YouTube', or anything else just because it is a music or video request. Your job is to obey the user EXACTLY.

13. COMPLEX COMMANDS: If the user says "open X and do Y", first figure out the PRIMARY intent:
    - "open reddit and send message" → the user wants to use REDDIT, not SMS. Use open_app with app_name="Reddit". Do NOT use send_sms.
    - "open X and search Y" → use youtube_search/spotify_search if X is YouTube/Spotify, otherwise open_app.
    - When the user mentions a specific app by name, ALWAYS use open_app for that app. Only use send_sms/send_whatsapp if the user explicitly wants to send an SMS text message or WhatsApp message WITHOUT mentioning another app.

14. APP DETECTION: If the user mentions ANY app name (Reddit, Twitter, Telegram, Discord, Instagram, Snapchat, etc.), use open_app with that app's name. Do NOT confuse app-based messaging with SMS.

15. SEND_SMS ONLY FOR ACTUAL SMS: Only use send_sms when the user explicitly wants to send an SMS text message via the default Messages app. If they say "send message on Reddit" or "message someone on Instagram", that is NOT an SMS — use open_app instead.

16. COMPLEX WEB TASKS: When the user asks you to search, find, download, or navigate to something on the web:
    - Use google_search with a smart query. The server will automatically execute the search AND open the first result on the device.
    - For example: "metrolist github apk download" → use google_search with query "metrolist github releases apk download"
    - For example: "XManager latest version download" → use google_search with query "XManager latest apk download github"
    - NEVER just say "I'm doing it" without choosing a proper action. Always pick google_search, open_url, or open_app.

17. ALWAYS EXECUTE: You must ALWAYS output a real action. Never output general_chat if the user clearly wants you to DO something (search, open, play, download, etc.). If unsure which action fits, use google_search to find what the user wants.

══════════════════════════════════════════════
EXAMPLES (follow these exactly):
══════════════════════════════════════════════

User: "open youtube"
Response: {"action":"open_app","execution_target":"device","params":{"app_name":"YouTube"},"response_text":"YouTube khul raha hai.","language":"en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"com.google.android.youtube"}

User: "YouTube pe sickkid search karo"
Response: {"action":"youtube_search","execution_target":"device","params":{"query":"sickkid"},"response_text":"YouTube pe sickkid search kar raha hoon.","language":"hi-en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"youtube"}

User: "open youtube and search sickkid"
Response: {"action":"youtube_search","execution_target":"device","params":{"query":"sickkid"},"response_text":"Searching sickkid on YouTube.","language":"en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"youtube"}

User: "spotify pe arijit singh sunao"
Response: {"action":"spotify_search","execution_target":"device","params":{"query":"arijit singh","type":"artist"},"response_text":"Spotify pe Arijit Singh search kar raha hoon.","language":"hi-en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"spotify"}

User: "google pe iphone 16 price search karo"
Response: {"action":"open_url","execution_target":"device","params":{"url":"https://www.google.com/search?q=iphone+16+price"},"response_text":"Google pe iphone 16 price search kar raha hoon.","language":"hi-en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"browser"}

User: "WhatsApp kholo"
Response: {"action":"open_app","execution_target":"device","params":{"app_name":"WhatsApp"},"response_text":"WhatsApp khul raha hai.","language":"hi","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"whatsapp"}

User: "Google pe jake metrolist github pe ja waha uski apk download kar"
Response: {"action":"google_search","execution_target":"server","params":{"query":"metrolist github releases apk download","num_results":3},"response_text":"Metrolist ka GitHub page search kar raha hoon aur APK dhundh raha hoon.","language":"hi-en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":null}

User: "XManager download karo latest version"
Response: {"action":"google_search","execution_target":"server","params":{"query":"XManager latest apk download","num_results":3},"response_text":"XManager ka latest version search kar raha hoon.","language":"hi-en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":null}

User: "Open reddit and send message to opening farm 6071 that this is a test"
Response: {"action":"open_app","execution_target":"device","params":{"app_name":"Reddit"},"response_text":"Reddit khol raha hoon. Waha jaake opening farm 6071 ko message bhejo.","language":"en","confidence":1.0,"confirmation_required":false,"confirmation_message":null,"app":"reddit"}
"""

# ── Actions that execute on device (Android app handles these) ─────────────────
DEVICE_ACTIONS = {
    "send_whatsapp", "make_call", "send_sms", "set_timer", "set_alarm",
    "upi_payment", "open_app", "take_screenshot", "set_volume",
    "youtube_search", "spotify_search", "open_url",
    "set_brightness", "toggle_wifi", "toggle_bluetooth",
    "click_element", "write_text",
}

# ── Actions that require confirmation ─────────────────────────────────────────
CONFIRMATION_REQUIRED_ACTIONS = {
    "upi_payment", "send_whatsapp", "make_call", "send_sms",
}


def _call_claude(messages: list[dict], system: str, max_tokens: int, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CONFIG.LLM_MODEL or "claude-3-5-sonnet-20241022",
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text

def _call_openai(messages: list[dict], system: str, max_tokens: int, api_key: str) -> str:
    import openai
    client = openai.OpenAI(api_key=api_key)
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    response = client.chat.completions.create(
        model=CONFIG.LLM_MODEL or "gpt-4o",
        messages=full_messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

def _call_groq(messages: list[dict], system: str, max_tokens: int, api_key: str) -> str:
    import groq
    client = groq.Groq(api_key=api_key)
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    response = client.chat.completions.create(
        model=CONFIG.LLM_MODEL or "llama-3.3-70b-versatile",
        messages=full_messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

def _call_gemini(messages: list[dict], system: str, max_tokens: int, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    
    gemini_msgs = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        gemini_msgs.append({"role": role, "parts": [m["content"]]})
        
    model = genai.GenerativeModel(
        model_name=CONFIG.LLM_MODEL or "gemini-2.5-flash",
        system_instruction=system if system else None
    )
    
    generation_config = genai.types.GenerationConfig(max_output_tokens=max_tokens)
    response = model.generate_content(gemini_msgs, generation_config=generation_config)
    return response.text

def _is_quota_error(e: Exception) -> bool:
    err_str = str(e).lower()
    # 429 = Too Many Requests / Quota Exceeded
    # 401 / 403 = Unauthorized / Forbidden (invalid key, out of credits)
    # resource exhausted = Google specific
    return any(x in err_str for x in ["429", "401", "403", "quota", "rate limit", "resource exhausted", "insufficient_quota"])

def call_llm(messages: list[dict], system: str = "", max_tokens: int = 1024) -> str:
    """Route LLM call to the configured provider, handling quota exhaustion by cycling keys."""
    provider = CONFIG.LLM_PROVIDER
    
    while True:
        key = CONFIG.get_active_llm_key()
        if not key:
            raise RuntimeError(f"No valid API keys remaining for {provider}")
            
        try:
            if provider == "openai":
                return _call_openai(messages, system, max_tokens, key)
            elif provider == "gemini":
                return _call_gemini(messages, system, max_tokens, key)
            elif provider == "groq":
                return _call_groq(messages, system, max_tokens, key)
            else:
                return _call_claude(messages, system, max_tokens, key)
        except Exception as e:
            if _is_quota_error(e):
                logger.warning("Key exhausted for %s (Error: %s). Cycling to next key...", provider, e)
                CONFIG.mark_key_finished(key)
                continue
            raise


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

    dynamic_prompt = SYSTEM_PROMPT
    try:
        apps_fact = await get_fact("installed_apps")
        if apps_fact:
            apps_list_json = apps_fact["value"]
            dynamic_prompt += f"\n\nUSER'S INSTALLED APPS (JSON List):\n{apps_list_json}\nWhen the user wants to open an app (even with a slang/abbreviation), match it exactly to one of the 'name's in this list in your response."
    except Exception as e:
        logger.warning(f"Could not load installed apps fact: {e}")

    # Call Claude with retry
    start = time.time()
    try:
        def _api_call() -> str:
            return call_llm(claude_msgs, system=dynamic_prompt)

        raw = retry_with_backoff(_api_call, max_retries=3, base_delay=1.0)
    except Exception as exc:
        provider = getattr(CONFIG, "LLM_PROVIDER", "LLM")
        logger.error("%s API failed after retries (session=%s): %s", provider, session_id[:8], exc)
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
