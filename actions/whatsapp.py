"""
actions/whatsapp.py — WhatsApp message sending via pywhatkit.
Resolves contact names to phone numbers via the contacts table in memory.
On headless VPS, requires Xvfb (virtual display) to run WhatsApp Web in a browser.
Always confirms before sending when brain confidence < 0.9.
"""

import logging
import os
import re
import time
from typing import Any, Optional

from config import CONFIG
from memory import find_contact_by_name

logger = logging.getLogger(__name__)


def _sanitize_number(phone: str) -> str:
    """
    Strip all non-digit characters from a phone number except leading '+'.

    Args:
        phone: Raw phone number string.

    Returns:
        Cleaned phone number (e.g. '+919876543210').
    """
    phone = phone.strip()
    if not phone.startswith("+"):
        # Assume Indian number if no country code
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            return "+91" + digits
        return "+" + digits
    return "+" + re.sub(r"\D", "", phone)


def _ensure_display() -> None:
    """
    Ensure a virtual X display is available on headless Linux servers.
    Starts Xvfb on :99 if DISPLAY is not set and HEADLESS_MODE is true.
    """
    if CONFIG.HEADLESS_MODE and os.name != "nt":
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":99"
            try:
                import subprocess
                subprocess.Popen(
                    ["Xvfb", ":99", "-screen", "0", "1280x720x24"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(1.5)
                logger.info("Started Xvfb virtual display on :99")
            except Exception as exc:
                logger.warning("Could not start Xvfb: %s", exc)


async def _resolve_contact(contact_name: str) -> Optional[str]:
    """
    Resolve a contact name to a phone number from the contacts table.

    Args:
        contact_name: Partial or full contact name.

    Returns:
        Phone number string, or None if contact not found.
    """
    contact = await find_contact_by_name(contact_name)
    if contact:
        return contact.get("phone")
    return None


async def send_message(
    contact: str,
    message: str,
    confidence: float = 1.0,
) -> dict[str, Any]:
    """
    Send a WhatsApp message to a contact.

    If confidence < 0.9, returns a confirmation request instead of sending.
    The recipient is resolved from the contacts table; if not found, contact is
    treated as a raw phone number.

    Args:
        contact: Contact name or phone number.
        message: The message text to send.
        confidence: Brain confidence score (0–1). Below 0.9 triggers confirmation.

    Returns:
        Dict with keys: success, action (sent|needs_confirmation|error), details.
    """
    if confidence < 0.9:
        return {
            "success": False,
            "action": "needs_confirmation",
            "details": {
                "contact": contact,
                "message": message,
                "question": f"Should I send '{message[:60]}' to {contact}?",
            },
        }

    # Resolve contact
    phone = await _resolve_contact(contact)
    if not phone:
        # Use contact directly as phone number
        phone = contact

    try:
        phone = _sanitize_number(phone)
    except Exception:
        return {"success": False, "action": "error", "error": f"Invalid phone number: {contact}"}

    _ensure_display()

    try:
        import pywhatkit  # type: ignore[import]

        # pywhatkit requires WhatsApp Web to be open in a browser
        # sendwhatmsg_instantly sends immediately without waiting for a scheduled time
        pywhatkit.sendwhatmsg_instantly(
            phone,
            message,
            wait_time=12,
            tab_close=True,
            close_time=3,
        )
        logger.info("WhatsApp message sent to %s", _mask_phone(phone))
        return {
            "success": True,
            "action": "sent",
            "details": {"phone": _mask_phone(phone), "chars": len(message)},
        }
    except ImportError:
        return {
            "success": False,
            "action": "error",
            "error": "pywhatkit is not installed.",
        }
    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)
        return {
            "success": False,
            "action": "error",
            "error": str(exc),
        }


async def send_image(
    contact: str,
    image_path: str,
    caption: str = "",
    confidence: float = 1.0,
) -> dict[str, Any]:
    """
    Send a WhatsApp image to a contact.

    Args:
        contact: Contact name or phone number.
        image_path: Absolute path to the image file.
        caption: Optional image caption.
        confidence: Brain confidence score. Below 0.9 triggers confirmation.

    Returns:
        Dict with keys: success, action, details.
    """
    if confidence < 0.9:
        return {
            "success": False,
            "action": "needs_confirmation",
            "details": {
                "contact": contact,
                "image": image_path,
                "question": f"Should I send the image to {contact}?",
            },
        }

    phone = await _resolve_contact(contact) or contact
    try:
        phone = _sanitize_number(phone)
    except Exception:
        return {"success": False, "action": "error", "error": f"Invalid phone: {contact}"}

    _ensure_display()

    try:
        import pywhatkit  # type: ignore[import]

        pywhatkit.sendwhats_image(phone, image_path, caption)
        logger.info("WhatsApp image sent to %s", _mask_phone(phone))
        return {
            "success": True,
            "action": "sent",
            "details": {"phone": _mask_phone(phone), "image": image_path},
        }
    except ImportError:
        return {"success": False, "action": "error", "error": "pywhatkit not installed."}
    except Exception as exc:
        logger.error("WhatsApp image send failed: %s", exc)
        return {"success": False, "action": "error", "error": str(exc)}


def _mask_phone(phone: str) -> str:
    """Return a masked phone number for safe logging."""
    clean = re.sub(r"\D", "", phone)
    if len(clean) >= 4:
        return "+" + "X" * (len(clean) - 4) + clean[-4:]
    return "XXXX"
