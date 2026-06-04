"""
utils/retry.py — Exponential backoff retry decorator/helper for Jarvis.
Used by brain.py (Claude API), search.py (SerpAPI), downloader.py (HTTP).
"""

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
) -> T:
    """
    Call func() up to max_retries times, with exponential backoff between attempts.
    Doubles the delay on each failure: base_delay → 2*base_delay → 4*base_delay…

    Args:
        func: Zero-argument callable to retry.
        max_retries: Maximum number of attempts (default 3).
        base_delay: Initial delay in seconds before first retry (default 1.0).
        max_delay: Maximum delay between retries (default 30.0 seconds).
        exceptions: Tuple of exception types to catch and retry on.

    Returns:
        The return value of func() on the first successful call.

    Raises:
        The last exception raised by func() if all retries are exhausted.
    """
    last_exc: Exception = RuntimeError("No attempts made")
    delay = base_delay

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except exceptions as exc:
            last_exc = exc
            if attempt == max_retries:
                logger.error(
                    "All %d retries exhausted. Last error: %s", max_retries, exc
                )
                break
            sleep_for = min(delay, max_delay)
            logger.warning(
                "Attempt %d/%d failed (%s). Retrying in %.1fs…",
                attempt, max_retries, exc, sleep_for,
            )
            time.sleep(sleep_for)
            delay *= 2.0  # exponential backoff

    raise last_exc
