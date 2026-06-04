"""
actions/weather.py — Weather information via wttr.in (no API key required).
Results are cached in Redis for WEATHER_CACHE_TTL seconds (default 30 minutes).
Generates a spoken natural language response in the user's detected language.
"""

import hashlib
import json
import logging
from typing import Any

import requests

from config import CONFIG

logger = logging.getLogger(__name__)

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


def _cache_key(city: str) -> str:
    """Derive a Redis cache key for a city's weather."""
    return f"jarvis:weather:{hashlib.md5(city.lower().strip().encode()).hexdigest()}"


def _get_cached(city: str) -> dict | None:
    """Return cached weather data from Redis, or None."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_cache_key(city))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _set_cached(city: str, data: dict) -> None:
    """Cache weather data in Redis with WEATHER_CACHE_TTL."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(_cache_key(city), CONFIG.WEATHER_CACHE_TTL, json.dumps(data))
    except Exception:
        pass


def _build_spoken_response(raw: dict, city: str, language: str) -> str:
    """
    Build a natural language weather summary in the user's language.

    Args:
        raw: Parsed weather data dict.
        city: City name.
        language: Language code (e.g. 'hi', 'en').

    Returns:
        Spoken weather response string.
    """
    temp = raw.get("temp_c", "?")
    feels = raw.get("feels_like_c", "?")
    cond = raw.get("condition", "")
    humidity = raw.get("humidity_pct", "?")
    wind = raw.get("wind_kph", "?")

    if language.startswith("hi"):
        return (
            f"{city} mein abhi {temp}°C hai, feel {feels}°C jaisa ho raha hai. "
            f"Mausam {cond} hai. Humidity {humidity}% aur hawa {wind} km/h ki speed se chal rahi hai."
        )
    return (
        f"It's currently {temp}°C in {city}, feels like {feels}°C. "
        f"Conditions: {cond}. Humidity is {humidity}% with {wind} km/h winds."
    )


async def get_weather(city: str, language: str = "en") -> dict[str, Any]:
    """
    Fetch current weather for a city using the wttr.in free JSON API.
    No API key required. Results are cached for WEATHER_CACHE_TTL seconds.

    Args:
        city: City name (e.g. 'Mumbai', 'Delhi', 'New York').
        language: Language code for the spoken response.

    Returns:
        Dict with keys:
          success (bool)
          spoken_response (str)   — natural language weather summary
          city (str)              — resolved city name
          cached (bool)
          raw (dict):
            temp_c, feels_like_c, condition, humidity_pct, wind_kph, visibility_km
    """
    city = city.strip()
    if not city:
        return {"success": False, "error": "City name is required."}

    # Cache hit
    cached = _get_cached(city)
    if cached:
        spoken = _build_spoken_response(cached, cached.get("city", city), language)
        return {"success": True, "spoken_response": spoken, "city": cached.get("city", city),
                "cached": True, "raw": cached}

    try:
        url = f"https://wttr.in/{requests.utils.quote(city)}?format=j1"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Jarvis/1.0"})
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Weather service timed out. Try again shortly."}
    except requests.exceptions.RequestException as exc:
        return {"success": False, "error": f"Weather fetch failed: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error: {exc}"}

    try:
        current = data["current_condition"][0]
        area_info = data.get("nearest_area", [{}])[0]
        resolved_city = (
            area_info.get("areaName", [{}])[0].get("value", city)
            + ", "
            + area_info.get("country", [{}])[0].get("value", "")
        ).strip(", ")

        raw = {
            "city": resolved_city,
            "temp_c": int(current["temp_C"]),
            "feels_like_c": int(current["FeelsLikeC"]),
            "condition": current["weatherDesc"][0]["value"],
            "humidity_pct": int(current["humidity"]),
            "wind_kph": int(current["windspeedKmph"]),
            "visibility_km": int(current.get("visibility", 0)),
        }
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Weather data parse error for '%s': %s", city, exc)
        return {"success": False, "error": "Could not parse weather data."}

    _set_cached(city, raw)
    spoken = _build_spoken_response(raw, resolved_city, language)
    return {
        "success": True,
        "spoken_response": spoken,
        "city": resolved_city,
        "cached": False,
        "raw": raw,
    }
