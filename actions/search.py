"""
actions/search.py — Google search via SerpAPI with BeautifulSoup scraping,
Claude summarisation in the user's language, and Redis result caching.
Cache TTL: SEARCH_CACHE_TTL seconds (default 10 minutes).
"""

import hashlib
import json
import logging
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import CONFIG
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# ── Redis cache ────────────────────────────────────────────────────────────────
_redis = None


def _get_redis():
    """Return a Redis client or None if unavailable."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as _r  # type: ignore[import]
        client = _r.from_url(CONFIG.REDIS_URL, decode_responses=True, socket_timeout=2)
        client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


def _cache_key(query: str) -> str:
    """Derive a Redis cache key from a search query."""
    digest = hashlib.md5(query.lower().strip().encode()).hexdigest()
    return f"jarvis:search:{digest}"


def _get_cached(query: str) -> list | None:
    """Return cached search results from Redis, or None."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_cache_key(query))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _set_cached(query: str, results: list) -> None:
    """Store search results in Redis with configured TTL."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(_cache_key(query), CONFIG.SEARCH_CACHE_TTL, json.dumps(results))
    except Exception as exc:
        logger.debug("Search cache write failed: %s", exc)


# ── SerpAPI fetch ──────────────────────────────────────────────────────────────

def _serpapi_fetch(query: str, num: int = 5) -> list[dict]:
    """
    Fetch organic search results from SerpAPI.

    Args:
        query: The search query string.
        num: Number of results to return.

    Returns:
        List of dicts with keys: title, url, snippet.

    Raises:
        RuntimeError if SERPAPI_KEY is not configured.
        requests.HTTPError on API errors.
    """
    if not CONFIG.has_serpapi():
        raise RuntimeError("SerpAPI key not configured.")
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={"q": query, "api_key": CONFIG.SERPAPI_KEY, "num": num, "gl": "in"},
        timeout=15,
    )
    resp.raise_for_status()
    organic = resp.json().get("organic_results", [])
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in organic[:num]
    ]


# ── BeautifulSoup scraper ──────────────────────────────────────────────────────

def _scrape(url: str, max_chars: int = 2000) -> str:
    """
    Scrape visible text content from a URL.
    Strips nav, script, style, footer elements.

    Args:
        url: The page URL to fetch.
        max_chars: Maximum characters of text to extract.

    Returns:
        Extracted text (truncated to max_chars), or empty string on failure.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Jarvis/1.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        import re
        text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
        return text[:max_chars]
    except Exception as exc:
        logger.debug("Scrape failed for %s: %s", url[:80], exc)
        return ""


# ── Claude summariser ──────────────────────────────────────────────────────────

def _summarise(query: str, results: list[dict], scraped: str, language: str) -> str:
    """
    Use Claude to produce a concise, natural-language answer from search results.
    Response is written in the user's detected language.

    Args:
        query: The original search query.
        results: List of SerpAPI result dicts.
        scraped: Scraped text from the top result.
        language: Language code for the response (e.g. 'hi', 'en').

    Returns:
        A 2–4 sentence summary in the target language.
    """
    try:
        import anthropic  # type: ignore[import]
        snippets = "\n".join(f"- {r['title']}: {r['snippet']}" for r in results[:5])
        prompt = (
            f"User searched for: '{query}'\n\n"
            f"Search snippets:\n{snippets}\n\n"
            f"Top result text (excerpt):\n{scraped}\n\n"
            f"Give a helpful 2-4 sentence answer in language code '{language}'. "
            "Be direct and informative. Do not mention sources."
        )
        client = anthropic.Anthropic(api_key=CONFIG.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=CONFIG.CLAUDE_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        logger.warning("Claude summarisation failed: %s", exc)
        return results[0]["snippet"] if results else "No results found."


# ── Public API ─────────────────────────────────────────────────────────────────

async def google_search(
    query: str,
    num_results: int = 5,
    language: str = "en",
) -> dict[str, Any]:
    """
    Perform a Google search, scrape the top result, and summarise with Claude.
    Results are cached in Redis for SEARCH_CACHE_TTL seconds.

    Args:
        query: The user's search query.
        num_results: Number of organic results to retrieve (default 5).
        language: Language code for the summary response.

    Returns:
        Dict with keys:
          success (bool)
          summary (str)         — Claude-generated spoken answer
          sources (list)        — [{title, url, snippet}]
          cached (bool)         — whether result came from cache
          query (str)
    """
    if not CONFIG.has_serpapi():
        return {
            "success": False,
            "error": "Google Search is not configured. Set SERPAPI_KEY in .env",
            "code": "FEATURE_UNAVAILABLE",
        }

    query = query.strip()[:500]

    # Cache hit
    cached = _get_cached(query)
    if cached:
        logger.info("Search cache hit: %s", query[:60])
        return {
            "success": True,
            "query": query,
            "summary": cached[0].get("snippet", "") if cached else "",
            "sources": cached,
            "cached": True,
        }

    # Fetch
    try:
        results = retry_with_backoff(
            lambda: _serpapi_fetch(query, num_results), max_retries=2
        )
    except Exception as exc:
        logger.error("SerpAPI failed: %s", exc)
        return {"success": False, "error": f"Search failed: {exc}"}

    if not results:
        return {"success": True, "query": query, "summary": "No results found.", "sources": [], "cached": False}

    scraped = _scrape(results[0]["url"]) if results else ""
    summary = _summarise(query, results, scraped, language)
    _set_cached(query, results)

    return {
        "success": True,
        "query": query,
        "summary": summary,
        "sources": results,
        "cached": False,
    }
