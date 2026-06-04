"""
utils/file_utils.py — File system utilities for Jarvis downloads and paths.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

DANGEROUS_EXTENSIONS = {".exe", ".bat", ".sh", ".msi", ".cmd", ".ps1", ".vbs", ".jar", ".apk"}


def get_filename_from_url(url: str) -> str:
    """
    Extract a clean filename from a URL.
    Falls back to a timestamped name if no filename is detectable.

    Args:
        url: The source URL.

    Returns:
        A sanitised filename string.
    """
    parsed = urlparse(url)
    raw = unquote(os.path.basename(parsed.path))
    # Sanitise: remove characters illegal in filenames
    name = re.sub(r'[\\/:*?"<>|]', "_", raw).strip()
    if name and "." in name:
        return name
    return f"download_{int(time.time())}"


def is_dangerous_file(filename: str) -> bool:
    """
    Check whether a filename has a potentially dangerous extension.

    Args:
        filename: The filename to inspect.

    Returns:
        True if the extension is in DANGEROUS_EXTENSIONS.
    """
    return Path(filename).suffix.lower() in DANGEROUS_EXTENSIONS


def list_files_in_dir(directory: str) -> list[dict]:
    """
    List all files in a directory with metadata.

    Args:
        directory: Absolute path to the directory.

    Returns:
        List of dicts with keys: filename, size_bytes, size_human, modified_iso.
    """
    from utils.audio_utils import human_readable_size
    from datetime import datetime, timezone

    d = Path(directory)
    files = []
    if d.exists():
        for f in sorted(d.iterdir()):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "filename": f.name,
                    "size_bytes": stat.st_size,
                    "size_human": human_readable_size(stat.st_size),
                    "modified_iso": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
    return files


def ensure_session_dir(base_dir: str, session_id: str) -> Path:
    """
    Ensure a per-session subdirectory exists inside base_dir.

    Args:
        base_dir: The root downloads folder.
        session_id: The session identifier (used as subdirectory name).

    Returns:
        Path object for the session's subdirectory.
    """
    # Sanitise session_id for use as a directory name
    safe_id = re.sub(r"[^\w\-]", "", session_id)[:32] or "default"
    d = Path(base_dir) / safe_id
    d.mkdir(parents=True, exist_ok=True)
    return d
