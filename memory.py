"""
memory.py — Persistent storage for Jarvis.
SQLite (WAL mode, async via aiosqlite) for long-term storage.
Redis for fast session history, search cache, and rate-limit counters.

Tables:
  conversations — per-session chat history
  facts         — key/value facts the user teaches Jarvis
  contacts      — address book with phone + UPI ID
  downloads     — file download records with progress
  intent_log    — every classified intent (for analytics + Android audit)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from config import CONFIG

logger = logging.getLogger(__name__)
DB = CONFIG.DB_PATH

# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    role        TEXT    NOT NULL CHECK(role IN ('user','assistant','system')),
    content     TEXT    NOT NULL,
    language    TEXT    DEFAULT 'en',
    action      TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT,
    whatsapp    INTEGER NOT NULL DEFAULT 0,
    upi_id      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    filename        TEXT    NOT NULL,
    filetype        TEXT    NOT NULL DEFAULT 'file',
    status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','downloading','completed','failed')),
    progress        REAL    NOT NULL DEFAULT 0.0,
    file_size_mb    REAL    DEFAULT 0.0,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS intent_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL,
    timestamp        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    action           TEXT    NOT NULL,
    execution_target TEXT    NOT NULL DEFAULT 'server',
    params_json      TEXT,
    success          INTEGER NOT NULL DEFAULT 1,
    error_msg        TEXT
);

CREATE INDEX IF NOT EXISTS idx_conv_session   ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_dl_status      ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_intent_session ON intent_log(session_id);
"""


async def init_db() -> None:
    """
    Initialise the SQLite database — create all tables and indexes.
    Should be called once at application startup via FastAPI lifespan.
    """
    async with aiosqlite.connect(DB) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    logger.info("SQLite database ready at %s", DB)


# ── Redis helpers ──────────────────────────────────────────────────────────────

_redis = None


def _get_redis():
    """
    Return a lazily-initialised Redis client, or None if Redis is unavailable.
    Failures are swallowed — the system degrades to SQLite-only mode.
    """
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as _r  # type: ignore[import]
        client = _r.from_url(CONFIG.REDIS_URL, decode_responses=True, socket_timeout=2)
        client.ping()
        _redis = client
        logger.info("Redis connected: %s", CONFIG.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — using SQLite only.", exc)
        _redis = None
    return _redis


def _rkey_history(session_id: str) -> str:
    """Redis key for a session's conversation history."""
    return f"jarvis:hist:{session_id}"


# ── Conversations ──────────────────────────────────────────────────────────────

async def save_message(
    session_id: str,
    role: str,
    content: str,
    language: str = "en",
    action: Optional[str] = None,
) -> None:
    """
    Persist a single conversation turn to SQLite.

    Args:
        session_id: Unique session identifier.
        role: One of 'user', 'assistant', 'system'.
        content: Message text (truncated to MAX_INPUT_LENGTH).
        language: Detected language code.
        action: Classified action name (assistant turns only).
    """
    content = content[: CONFIG.MAX_INPUT_LENGTH]
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, language, action) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, language, action),
        )
        await db.commit()


async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """
    Retrieve conversation history for a session.
    Checks Redis first (fast); falls back to SQLite.

    Args:
        session_id: The session to retrieve history for.
        limit: Maximum number of messages to return.

    Returns:
        List of message dicts ordered oldest → newest.
    """
    r = _get_redis()
    if r:
        try:
            raw = r.get(_rkey_history(session_id))
            if raw:
                return json.loads(raw)[-limit:]
        except Exception:
            pass

    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT role, content, language, action, timestamp
               FROM conversations
               WHERE session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in reversed(rows)]


def cache_session_history(session_id: str, history: list[dict]) -> None:
    """
    Write session history to Redis with 24-hour TTL.

    Args:
        session_id: Session identifier.
        history: Full list of message dicts.
    """
    r = _get_redis()
    if not r:
        return
    try:
        trimmed = history[-(CONFIG.SESSION_HISTORY_LENGTH * 2):]
        r.setex(_rkey_history(session_id), CONFIG.SESSION_TTL, json.dumps(trimmed))
    except Exception as exc:
        logger.debug("Redis history write failed: %s", exc)


def get_cached_history(session_id: str) -> Optional[list[dict]]:
    """
    Retrieve session history from Redis.

    Args:
        session_id: Session identifier.

    Returns:
        List of message dicts, or None if not cached.
    """
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_rkey_history(session_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ── Facts ──────────────────────────────────────────────────────────────────────

async def save_fact(key: str, value: str) -> None:
    """
    Upsert a fact into the facts table.

    Args:
        key: Fact identifier (e.g. 'rahul_upi').
        value: Fact value (e.g. 'rahul@okaxis').
    """
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """INSERT INTO facts (key, value)
               VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE
               SET value=excluded.value,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
            (key, value),
        )
        await db.commit()


async def get_fact(key: str) -> Optional[dict]:
    """
    Retrieve a single fact by key.

    Args:
        key: The fact key to look up.

    Returns:
        Dict with keys id, key, value, created_at, updated_at — or None.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, key, value, created_at, updated_at FROM facts WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_fact(key: str) -> bool:
    """
    Delete a fact by key.

    Args:
        key: The fact key to delete.

    Returns:
        True if a row was deleted.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("DELETE FROM facts WHERE key=?", (key,))
        await db.commit()
        return cur.rowcount > 0


async def list_facts() -> list[dict]:
    """
    Return all stored facts ordered by key.

    Returns:
        List of fact dicts.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, key, value, created_at, updated_at FROM facts ORDER BY key"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Contacts ───────────────────────────────────────────────────────────────────

async def save_contact(
    name: str,
    phone: Optional[str] = None,
    whatsapp: bool = False,
    upi_id: Optional[str] = None,
) -> int:
    """
    Add a new contact.

    Args:
        name: Full contact name.
        phone: Phone number in any format.
        whatsapp: Whether this contact is on WhatsApp.
        upi_id: UPI payment ID (e.g. 'rahul@okaxis').

    Returns:
        Newly created contact ID.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO contacts (name, phone, whatsapp, upi_id) VALUES (?,?,?,?)",
            (name, phone, int(whatsapp), upi_id),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_contact(contact_id: int) -> Optional[dict]:
    """
    Retrieve a contact by ID.

    Args:
        contact_id: Numeric contact ID.

    Returns:
        Contact dict or None.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, phone, whatsapp, upi_id, created_at FROM contacts WHERE id=?",
            (contact_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def search_contacts(query: str) -> list[dict]:
    """
    Search contacts by name (case-insensitive partial match).

    Args:
        query: Partial name to search for.

    Returns:
        List of matching contact dicts.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, phone, whatsapp, upi_id, created_at "
            "FROM contacts WHERE name LIKE ? ORDER BY name",
            (f"%{query}%",),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def list_contacts() -> list[dict]:
    """
    Return all contacts ordered by name.

    Returns:
        List of contact dicts.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, phone, whatsapp, upi_id, created_at FROM contacts ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def update_contact(
    contact_id: int,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    whatsapp: Optional[bool] = None,
    upi_id: Optional[str] = None,
) -> bool:
    """
    Update one or more fields of a contact.

    Args:
        contact_id: The contact to update.
        name: New name (or None to leave unchanged).
        phone: New phone number.
        whatsapp: New WhatsApp flag.
        upi_id: New UPI ID.

    Returns:
        True if the contact was found and updated.
    """
    fields, vals = [], []
    if name is not None:
        fields.append("name=?"); vals.append(name)
    if phone is not None:
        fields.append("phone=?"); vals.append(phone)
    if whatsapp is not None:
        fields.append("whatsapp=?"); vals.append(int(whatsapp))
    if upi_id is not None:
        fields.append("upi_id=?"); vals.append(upi_id)
    if not fields:
        return False
    vals.append(contact_id)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            f"UPDATE contacts SET {','.join(fields)} WHERE id=?", vals  # noqa: S608
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_contact(contact_id: int) -> bool:
    """
    Delete a contact by ID.

    Args:
        contact_id: The contact to delete.

    Returns:
        True if a row was deleted.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        await db.commit()
        return cur.rowcount > 0


# ── Downloads ──────────────────────────────────────────────────────────────────

async def save_download(url: str, filename: str, filetype: str = "file") -> int:
    """
    Create a new download record.

    Args:
        url: Source URL.
        filename: Target filename.
        filetype: 'file' or 'video'.

    Returns:
        Newly created download ID.
    """
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO downloads (url, filename, filetype) VALUES (?,?,?)",
            (url, filename, filetype),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def update_download_progress(
    download_id: int,
    progress: float,
    status: str,
    file_size_mb: float = 0.0,
    completed_at: Optional[datetime] = None,
) -> None:
    """
    Update a download's progress and status.

    Args:
        download_id: The download record to update.
        progress: Completion percentage (0–100).
        status: One of 'pending', 'downloading', 'completed', 'failed'.
        file_size_mb: File size in megabytes.
        completed_at: UTC datetime when the download finished.
    """
    completed_str = completed_at.isoformat() if completed_at else None
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE downloads SET progress=?, status=?, file_size_mb=?, completed_at=? WHERE id=?",
            (progress, status, file_size_mb, completed_str, download_id),
        )
        await db.commit()


async def get_download(download_id: int) -> Optional[dict]:
    """
    Retrieve a single download record.

    Args:
        download_id: The download ID.

    Returns:
        Download dict or None.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, url, filename, filetype, status, progress, "
            "file_size_mb, created_at, completed_at FROM downloads WHERE id=?",
            (download_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_downloads() -> list[dict]:
    """
    Return all download records, newest first.

    Returns:
        List of download dicts.
    """
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, url, filename, filetype, status, progress, "
            "file_size_mb, created_at, completed_at FROM downloads ORDER BY id DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Intent log ─────────────────────────────────────────────────────────────────

async def log_intent(
    session_id: str,
    action: str,
    execution_target: str,
    params: Optional[dict] = None,
    success: bool = True,
    error_msg: Optional[str] = None,
) -> None:
    """
    Log every classified intent for auditing and Android analytics.

    Args:
        session_id: The session that triggered this intent.
        action: Classified action name (e.g. 'send_whatsapp').
        execution_target: 'server' or 'device'.
        params: Intent parameters dict (will be JSON-serialised).
        success: Whether the intent was fulfilled successfully.
        error_msg: Error message if success is False.
    """
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO intent_log (session_id, action, execution_target, params_json, success, error_msg) "
            "VALUES (?,?,?,?,?,?)",
            (
                session_id,
                action,
                execution_target,
                json.dumps(params) if params else None,
                int(success),
                error_msg,
            ),
        )
        await db.commit()
