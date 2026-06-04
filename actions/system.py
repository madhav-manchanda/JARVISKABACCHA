"""
actions/system.py — VPS system information for Jarvis.
Uses psutil for CPU/RAM/disk/network stats.
Returns both a spoken response (for TTS) and raw data (for Android display).
"""

import logging
import platform
import time
from typing import Any

import psutil

logger = logging.getLogger(__name__)

_START_TIME = time.time()


def _spoken_info(raw: dict, language: str) -> str:
    """
    Format system info as a spoken summary in the user's language.

    Args:
        raw: System info dict from get_system_info.
        language: Language code for the response.

    Returns:
        Natural language system status string.
    """
    cpu = raw["cpu_percent"]
    ram_used = raw["memory"]["used_gb"]
    ram_total = raw["memory"]["total_gb"]
    ram_pct = raw["memory"]["percent"]
    disk_free = raw["disk"]["free_gb"]
    uptime_h = raw["uptime_hours"]

    if language.startswith("hi"):
        return (
            f"Server theek chal raha hai. CPU {cpu}% use ho raha hai. "
            f"RAM mein {ram_used:.1f} GB use ho raha hai, total {ram_total:.1f} GB hai, "
            f"{ram_pct}% used. Disk mein {disk_free:.1f} GB free hai. "
            f"Server {uptime_h:.1f} ghante se chal raha hai."
        )
    return (
        f"Server is running fine. CPU at {cpu}%, RAM {ram_used:.1f}/{ram_total:.1f} GB "
        f"({ram_pct}% used), {disk_free:.1f} GB disk free, "
        f"uptime {uptime_h:.1f} hours."
    )


async def get_system_info(language: str = "en") -> dict[str, Any]:
    """
    Collect VPS system metrics using psutil and format a spoken response.

    Args:
        language: Language code for the spoken summary.

    Returns:
        Dict with keys:
          success (bool)
          spoken_response (str)   — natural language system summary
          raw (dict):
            cpu_percent, cpu_count, memory (total_gb, used_gb, percent),
            disk (total_gb, used_gb, free_gb, percent),
            network (bytes_sent_mb, bytes_recv_mb),
            uptime_seconds, uptime_hours, jarvis_uptime_seconds,
            platform, hostname, python_version
    """
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot_ts = psutil.boot_time()
        uptime_s = int(time.time() - boot_ts)

        raw = {
            "cpu_percent": cpu_pct,
            "cpu_count": psutil.cpu_count(logical=True),
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / 1e9, 2),
                "used_gb": round(disk.used / 1e9, 2),
                "free_gb": round(disk.free / 1e9, 2),
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent_mb": round(net.bytes_sent / 1e6, 2),
                "bytes_recv_mb": round(net.bytes_recv / 1e6, 2),
            },
            "uptime_seconds": uptime_s,
            "uptime_hours": round(uptime_s / 3600, 2),
            "jarvis_uptime_seconds": int(time.time() - _START_TIME),
            "platform": platform.platform(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
        }

        return {
            "success": True,
            "spoken_response": _spoken_info(raw, language),
            "raw": raw,
        }

    except Exception as exc:
        logger.error("get_system_info failed: %s", exc)
        return {"success": False, "error": str(exc)}
