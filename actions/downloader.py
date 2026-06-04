"""
actions/downloader.py — Non-blocking file and video downloads for Jarvis VPS.
All downloads run in background threads; progress is tracked in SQLite.
WebSocket events are pushed on completion.
Warns before downloading dangerous file extensions.
yt-dlp is used for video/audio from supported platforms.
"""

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from config import CONFIG
from memory import save_download, update_download_progress
from utils.file_utils import (
    get_filename_from_url,
    is_dangerous_file,
    ensure_session_dir,
)

logger = logging.getLogger(__name__)

# ── WebSocket push ─────────────────────────────────────────────────────────────
_ws_callback: Optional[Callable] = None


def set_ws_callback(cb: Callable) -> None:
    """
    Register the WebSocket push callback (set by server.py on startup).
    Signature: cb(session_id: str, event: dict) — may be sync or async.

    Args:
        cb: Callable that pushes a JSON event to a WebSocket session.
    """
    global _ws_callback
    _ws_callback = cb


def _push(session_id: Optional[str], event: dict) -> None:
    """Fire-and-forget WebSocket push from a background thread."""
    if not _ws_callback or not session_id:
        return
    try:
        import asyncio
        if asyncio.iscoroutinefunction(_ws_callback):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_ws_callback(session_id, event))
            loop.close()
        else:
            _ws_callback(session_id, event)
    except Exception as exc:
        logger.debug("WS push failed: %s", exc)


# ── Video site detection ───────────────────────────────────────────────────────

_VIDEO_DOMAINS = re.compile(
    r"(youtube\.com|youtu\.be|instagram\.com|twitter\.com|x\.com|"
    r"tiktok\.com|facebook\.com|fb\.watch|vimeo\.com|dailymotion\.com|"
    r"twitch\.tv|reddit\.com/r/.*/comments)",
    re.IGNORECASE,
)


def detect_type(url: str) -> str:
    """
    Detect whether a URL points to a video/audio or a generic file.

    Args:
        url: The URL to inspect.

    Returns:
        'video' if the URL is from a known video platform, 'file' otherwise.
    """
    return "video" if _VIDEO_DOMAINS.search(url) else "file"


# ── Background download threads ────────────────────────────────────────────────

def _sync_update_progress(download_id: int, progress: float, status: str,
                           mb: float = 0.0, completed: Optional[datetime] = None) -> None:
    """Run the async update_download_progress synchronously from a thread."""
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(
        update_download_progress(download_id, progress, status, mb, completed)
    )
    loop.close()


def _file_thread(download_id: int, url: str, dest: Path,
                 session_id: Optional[str]) -> None:
    """
    Background thread: download a generic file via requests with streaming.
    Updates SQLite progress every 5 seconds. Pushes WS event on completion.

    Args:
        download_id: DB record ID.
        url: Source URL.
        dest: Absolute destination path.
        session_id: Session for WS events.
    """
    _sync_update_progress(download_id, 0.0, "downloading")
    try:
        headers = {"User-Agent": "Mozilla/5.0 Jarvis-Downloader/1.0"}
        with requests.get(url, stream=True, timeout=60, headers=headers) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            last_report = time.time()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_report >= 5:
                            pct = (downloaded / total * 100) if total else 0
                            _sync_update_progress(download_id, round(pct, 1), "downloading")
                            last_report = now

        size_mb = round(dest.stat().st_size / 1e6, 2)
        _sync_update_progress(download_id, 100.0, "completed", size_mb, datetime.now(timezone.utc))
        logger.info("Download complete [id=%d]: %s (%.2f MB)", download_id, dest.name, size_mb)
        _push(session_id, {
            "event": "download_complete",
            "data": {"download_id": download_id, "filename": dest.name, "file_size_mb": size_mb},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.error("File download failed [id=%d]: %s", download_id, exc)
        _sync_update_progress(download_id, 0.0, "failed")
        _push(session_id, {
            "event": "error",
            "data": {"download_id": download_id, "message": str(exc)},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _video_thread(download_id: int, url: str, dest_dir: Path,
                  session_id: Optional[str]) -> None:
    """
    Background thread: download a video/audio via yt-dlp.
    Pushes progress WS events and completion event.

    Args:
        download_id: DB record ID.
        url: Video page URL (YouTube, Instagram, etc.).
        dest_dir: Directory to save the downloaded file.
        session_id: Session for WS events.
    """
    _sync_update_progress(download_id, 0.0, "downloading")
    last_push_pct = -1.0

    def _hook(d: dict) -> None:
        nonlocal last_push_pct
        if d.get("status") == "downloading":
            pct_str = d.get("_percent_str", "0%").strip().rstrip("%")
            try:
                pct = float(pct_str)
                if pct - last_push_pct >= 10:
                    _sync_update_progress(download_id, pct, "downloading")
                    _push(session_id, {
                        "event": "download_progress",
                        "data": {"download_id": download_id, "progress_percent": pct},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    last_push_pct = pct
            except ValueError:
                pass

    try:
        import yt_dlp  # type: ignore[import]
        opts = {
            "outtmpl": str(dest_dir / "%(title).80s.%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        size_mb = round(Path(filename).stat().st_size / 1e6, 2) if Path(filename).exists() else 0.0
        _sync_update_progress(download_id, 100.0, "completed", size_mb, datetime.now(timezone.utc))
        logger.info("Video download complete [id=%d]: %s", download_id, filename)
        _push(session_id, {
            "event": "download_complete",
            "data": {
                "download_id": download_id,
                "filename": Path(filename).name,
                "file_size_mb": size_mb,
                "type": "video",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except ImportError:
        _sync_update_progress(download_id, 0.0, "failed")
        logger.error("yt-dlp not installed.")
    except Exception as exc:
        _sync_update_progress(download_id, 0.0, "failed")
        logger.error("Video download failed [id=%d]: %s", download_id, exc)


# ── Public API ─────────────────────────────────────────────────────────────────

async def download(url: str, session_id: str = "") -> dict[str, Any]:
    """
    Start a background download for any URL — auto-detects file vs video.
    Returns immediately with download_id; progress is tracked asynchronously.

    If the file has a dangerous extension (exe, bat, sh, apk, etc.),
    returns a warning requiring user confirmation before actually downloading.

    Args:
        url: Direct file URL or video page URL.
        session_id: Session identifier for per-session directories and WS events.

    Returns:
        Dict with keys:
          success (bool)
          download_id (int)         — DB record ID for progress polling
          status (str)              — 'started' or 'dangerous_file_warning'
          message (str)             — spoken response
          filename (str, optional)  — guessed filename
          warning (str, optional)   — shown if extension is dangerous
    """
    url = url.strip()
    dl_type = detect_type(url)

    if dl_type == "file":
        filename = get_filename_from_url(url)
        if is_dangerous_file(filename):
            ext = Path(filename).suffix
            return {
                "success": False,
                "status": "dangerous_file_warning",
                "needs_confirmation": True,
                "filename": filename,
                "warning": (
                    f"⚠️ '{filename}' has a potentially dangerous extension ({ext}). "
                    "Are you sure you want to download it? Reply 'yes download' to confirm."
                ),
                "url": url,
            }

        dest_dir = ensure_session_dir(CONFIG.DOWNLOAD_FOLDER, session_id)
        dest = dest_dir / filename
        download_id = await save_download(url, filename, "file")

        threading.Thread(
            target=_file_thread,
            args=(download_id, url, dest, session_id),
            daemon=True,
            name=f"dl-file-{download_id}",
        ).start()

        return {
            "success": True,
            "download_id": download_id,
            "status": "started",
            "filename": filename,
            "message": f"'{filename}' download shuru ho gayi hai. Complete hone par notify karunga.",
        }

    else:
        # Video
        dest_dir = ensure_session_dir(CONFIG.DOWNLOAD_FOLDER, session_id)
        download_id = await save_download(url, "video_pending", "video")

        threading.Thread(
            target=_video_thread,
            args=(download_id, url, dest_dir, session_id),
            daemon=True,
            name=f"dl-video-{download_id}",
        ).start()

        return {
            "success": True,
            "download_id": download_id,
            "status": "started",
            "message": "Video download shuru ho gayi hai. Complete hone par notify karunga.",
        }


async def get_progress(download_id: int) -> dict[str, Any]:
    """
    Get the current progress of a specific download.

    Args:
        download_id: The download record ID.

    Returns:
        Dict with keys: download_id, filename, progress_percent, status, file_size_mb.
        Returns error dict if download_id not found.
    """
    from memory import get_download
    row = await get_download(download_id)
    if not row:
        return {"success": False, "error": f"Download {download_id} not found."}
    return {
        "success": True,
        "download_id": row["id"],
        "filename": row["filename"],
        "progress_percent": row["progress"],
        "status": row["status"],
        "file_size_mb": row["file_size_mb"],
    }
