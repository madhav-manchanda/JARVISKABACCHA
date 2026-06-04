"""
config.py — Central configuration for Jarvis VPS.
Loads all settings from .env using python-dotenv.
Validates required keys at startup. Warns for missing optional ones.
Prints a feature availability summary on startup.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


class Config:
    """
    Single configuration object imported everywhere in Jarvis.
    All settings come from environment variables (loaded from .env).
    """

    # ── AI / Brain ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    # ── STT / TTS ──────────────────────────────────────────────────────────────
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "medium")
    TTS_ENGINE: str = os.getenv("TTS_ENGINE", "pyttsx3")          # pyttsx3 | elevenlabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")

    # ── Search / Scraping ──────────────────────────────────────────────────────
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")

    # ── Storage / Cache ────────────────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "jarvis.db"))

    # ── Security / Auth ────────────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    JARVIS_USERNAME: str = os.getenv("JARVIS_USERNAME", "admin")
    JARVIS_PASSWORD: str = os.getenv("JARVIS_PASSWORD", "")

    # ── Server ─────────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    VPS_DOMAIN: str = os.getenv("VPS_DOMAIN", "localhost")
    VERSION: str = "1.0.0"
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if o.strip()
    ]

    # ── Paths ──────────────────────────────────────────────────────────────────
    DOWNLOAD_FOLDER: str = os.getenv("DOWNLOAD_FOLDER", str(BASE_DIR / "downloads"))
    AUDIO_CACHE_FOLDER: str = os.getenv("AUDIO_CACHE_FOLDER", str(BASE_DIR / "audio_cache"))
    LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "jarvis.log"))
    DORK_AUDIT_LOG: str = os.getenv("DORK_AUDIT_LOG", str(BASE_DIR / "logs" / "dork_audit.log"))

    # ── Limits ─────────────────────────────────────────────────────────────────
    MAX_AUDIO_SIZE_MB: int = int(os.getenv("MAX_AUDIO_SIZE_MB", "25"))
    MAX_INPUT_LENGTH: int = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
    SESSION_HISTORY_LENGTH: int = int(os.getenv("SESSION_HISTORY_LENGTH", "20"))
    RATE_LIMIT: str = os.getenv("RATE_LIMIT", "60/minute")

    # ── Cache TTLs (seconds) ───────────────────────────────────────────────────
    SEARCH_CACHE_TTL: int = int(os.getenv("SEARCH_CACHE_TTL", "600"))    # 10 min
    WEATHER_CACHE_TTL: int = int(os.getenv("WEATHER_CACHE_TTL", "1800")) # 30 min
    AUDIO_CACHE_TTL: int = int(os.getenv("AUDIO_CACHE_TTL", "300"))      # 5 min
    SESSION_TTL: int = 86400                                               # 24 h

    # ── Feature Flags ──────────────────────────────────────────────────────────
    HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "true").lower() == "true"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── Required keys — app refuses to start if these are missing ──────────────
    _REQUIRED: list[str] = ["ANTHROPIC_API_KEY", "JWT_SECRET", "JARVIS_PASSWORD"]

    # ── Optional keys — warn if missing, disable related feature gracefully ────
    _OPTIONAL: list[str] = ["SERPAPI_KEY", "ELEVENLABS_API_KEY", "REDIS_URL"]

    # ──────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """
        Validate configuration at startup.
        Raises RuntimeError for any missing required key.
        Logs a warning for each missing optional key.
        Creates all required directories.
        Prints a feature-availability summary to stdout.
        """
        missing = [k for k in self._REQUIRED if not getattr(self, k)]
        if missing:
            raise RuntimeError(
                f"Missing required config keys: {missing}. "
                "Copy .env.example → .env and fill in the values."
            )

        for key in self._OPTIONAL:
            if not getattr(self, key):
                logger.warning(
                    "Optional config key '%s' not set — related feature disabled.", key
                )

        # Ensure all directories exist
        for attr in ["DOWNLOAD_FOLDER", "AUDIO_CACHE_FOLDER"]:
            Path(getattr(self, attr)).mkdir(parents=True, exist_ok=True)
        Path(self.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(self.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

        self._print_feature_summary()

    def _print_feature_summary(self) -> None:
        """Print a startup summary of which features are enabled/disabled."""
        features = {
            "Google Search (SerpAPI)":    self.has_serpapi(),
            "ElevenLabs TTS":             self.has_elevenlabs(),
            "Redis Session Cache":        bool(self.REDIS_URL),
            "Local TTS (pyttsx3)":        self.TTS_ENGINE == "pyttsx3",
            "Whisper STT":                True,  # always available if installed
        }
        print("\n" + "=" * 52)
        print("  Jarvis VPS — Feature Status")
        print("=" * 52)
        for name, enabled in features.items():
            status = "✓ ENABLED " if enabled else "✗ DISABLED"
            print(f"  {status}  {name}")
        print("=" * 52 + "\n")

    # ── Feature availability helpers ───────────────────────────────────────────

    def has_serpapi(self) -> bool:
        """Return True if SerpAPI key is configured."""
        return bool(self.SERPAPI_KEY)

    def has_elevenlabs(self) -> bool:
        """Return True if ElevenLabs API key AND voice ID are configured."""
        return bool(self.ELEVENLABS_API_KEY and self.ELEVENLABS_VOICE_ID)

    def has_redis(self) -> bool:
        """Return True if a Redis URL is configured."""
        return bool(self.REDIS_URL)


# Global singleton — imported as `from config import CONFIG`
CONFIG = Config()
