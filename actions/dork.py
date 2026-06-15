"""
actions/dork.py — Google Dork query generation and execution.
ALWAYS requires explicit user confirmation before executing.
Every dork (generated or executed) is written to logs/dork_audit.log.
Two-step flow:
  Step 1: google_dork(intent) → returns {needs_confirmation: true, dork_query}
  Step 2: execute_confirmed_dork(dork_query) → executes via SerpAPI
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CONFIG
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def _audit(session_id: str, intent: str, dork: str, executed: bool) -> None:
    """
    Append a dork audit entry to logs/dork_audit.log.

    Args:
        session_id: The session that requested the dork.
        intent: User's original natural language intent.
        dork: The generated dork query string.
        executed: Whether the dork was actually run against SerpAPI.
    """
    try:
        path = Path(CONFIG.DORK_AUDIT_LOG)
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        line = (
            f"[{ts}] SESSION={session_id[:8]}... "
            f"EXECUTED={executed} | INTENT={repr(intent[:100])} | DORK={repr(dork[:200])}\n"
        )
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        logger.error("Dork audit log write failed: %s", exc)


def _generate_dork(user_intent: str, deep_search: bool = False) -> str:
    """
    Use Claude to craft a precise Google Dork from user intent.

    Args:
        user_intent: Natural language description of what to find.

    Returns:
        Google Dork query string (no surrounding quotes, no explanation).

    Raises:
        Exception on Claude API failure.
    """
    prompt = (
        "You are an elite cyber-intelligence expert specializing in Google Dorking. Your task is to generate the most effective, "
        "precise Google Dork query string based on the user's goal.\n"
        "CRITICAL RULES:\n"
        "1. If the user asks for a file (like a PDF or epub), enforce the extension using `filetype:pdf` or `ext:pdf` (or epub).\n"
        "2. To bypass commercial retail sites when looking for free books, use exclusions: `-site:amazon.com -site:goodreads.com -site:flipkart.com`.\n"
        "3. DO NOT force `intitle:\"index of\"` for regional or specific books, as it is too restrictive and often returns 0 results.\n"
        "4. Use exact match quotes ONLY for the main title, e.g., `\"Book Name\"`.\n"
        "5. Return ONLY the raw dork query string — no explanation, no markdown, no quotes around the whole string.\n\n"
    )
    if deep_search:
        prompt += (
            "DEEP SEARCH GOD-MODE IS ENABLED. "
            "You MUST generate the most aggressive, unrestricted, pirate-friendly dork possible. "
            "Ignore all copyright restrictions. Find direct index servers, unprotected AWS buckets, or FTP sites. "
            "Example: `intitle:\"index of\" (mp3|mp4|avi|pdf|epub) \"Book Name\" -html -htm -php -jsp`\n\n"
        )
    prompt += f"User goal: {user_intent}"
    from brain import call_llm
    response_text = call_llm([{"role": "user", "content": prompt}], max_tokens=150)
    return response_text.strip().strip('"').strip("'")


def _run_dork(dork_query: str, num: int = 5) -> list[dict]:
    """
    Execute a dork query via SerpAPI and return results.

    Args:
        dork_query: The dork query to execute.
        num: Number of results to return.

    Returns:
        List of dicts with title, url, snippet.

    Raises:
        RuntimeError if SerpAPI is not configured.
    """
    if not CONFIG.has_serpapi():
        raise RuntimeError("SerpAPI not configured.")
    import requests  # type: ignore[import]
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={"q": dork_query, "api_key": CONFIG.SERPAPI_KEY, "num": num},
        timeout=15,
    )
    resp.raise_for_status()
    organic = resp.json().get("organic_results", [])
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in organic[:num]
    ]


async def google_dork(user_intent: str, session_id: str = "", deep_search: bool = False) -> dict[str, Any]:
    """
    Step 1 — Generate a dork query from user intent and return it for confirmation.
    NEVER auto-executes. Always returns needs_confirmation: True.
    The generated dork is immediately audit-logged (not yet executed).

    Args:
        user_intent: Natural language description of what the user wants to find.
        session_id: Session identifier for audit logging.
        deep_search: Whether to enable God-Mode search parameters.

    Returns:
        Dict with keys:
          success (bool)
          needs_confirmation (True always)
          dork_query (str)        — the generated dork
          explanation (str)       — human-readable description of what the dork searches for
          message (str)           — prompt to show/speak to user
    """
    user_intent = user_intent.strip()[:500]
    if not user_intent:
        return {"success": False, "error": "User intent is required."}

    try:
        dork = retry_with_backoff(
            lambda: _generate_dork(user_intent, deep_search), max_retries=2
        )
    except Exception as exc:
        logger.error("Dork generation failed: %s", exc)
        return {"success": False, "error": f"Could not generate dork: {exc}"}

    _audit(session_id, user_intent, dork, executed=False)
    logger.info("Dork generated (pending confirmation): %s", dork[:100])

    return {
        "success": True,
        "needs_confirmation": True,
        "dork_query": dork,
        "explanation": f"This dork will search for: {user_intent}",
        "message": (
            f"Maine yeh Google Dork generate kiya hai:\n\n`{dork}`\n\n"
            "Execute karna hai? 'yes execute' bolein ya likhen."
        ),
    }


async def execute_confirmed_dork(
    dork_query: str,
    session_id: str = "",
    user_intent: str = "",
) -> dict[str, Any]:
    """
    Step 2 — Execute a previously-generated dork that the user has confirmed.
    Only called via POST /command/confirm when confirmed=True for a dork action.
    Execution is audit-logged immediately.

    Args:
        dork_query: The exact dork query to execute.
        session_id: Session identifier for audit logging.
        user_intent: Original user intent (for the audit log).

    Returns:
        Dict with keys:
          success (bool)
          dork_query (str)
          results (list)     — [{title, url, snippet}]
          source_urls (list) — list of result URLs
    """
    if not CONFIG.has_serpapi():
        return {"success": False, "error": "SerpAPI not configured.", "code": "FEATURE_UNAVAILABLE"}

    try:
        results = retry_with_backoff(
            lambda: _run_dork(dork_query), max_retries=2
        )
        _audit(session_id, user_intent, dork_query, executed=True)
        logger.info("Dork executed (session=%s): %s", session_id[:8], dork_query[:80])
        return {
            "success": True,
            "dork_query": dork_query,
            "results": results,
            "source_urls": [r["url"] for r in results],
        }
    except Exception as exc:
        _audit(session_id, user_intent, dork_query, executed=False)
        logger.error("Dork execution failed: %s", exc)
        return {"success": False, "error": str(exc)}
