"""
utils/audio_utils.py — Audio format detection and validation helpers.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Supported audio MIME types and corresponding file extensions
SUPPORTED_AUDIO = {
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
    "video/webm": ".webm",  # WebM from browser MediaRecorder
}

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"}


def get_extension_from_content_type(content_type: str) -> Optional[str]:
    """
    Map a MIME content-type string to a file extension.

    Args:
        content_type: MIME type string (e.g. 'audio/mpeg').

    Returns:
        Extension string (e.g. '.mp3'), or None if unsupported.
    """
    ct = content_type.split(";")[0].strip().lower()
    return SUPPORTED_AUDIO.get(ct)


def is_allowed_audio(filename: str) -> bool:
    """
    Check if a filename has an allowed audio extension.

    Args:
        filename: The filename to check.

    Returns:
        True if the extension is in ALLOWED_EXTENSIONS.
    """
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def human_readable_size(size_bytes: int) -> str:
    """
    Convert a byte count to a human-readable string (KB, MB, GB).

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string (e.g. '4.2 MB').
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    return f"{size_bytes / 1024 ** 3:.1f} GB"
