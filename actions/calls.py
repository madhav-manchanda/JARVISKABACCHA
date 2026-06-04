"""
actions/calls.py — Outbound calls and SMS via Twilio.
Resolves contact names to phone numbers via the contacts table in memory.
Returns call SIDs for tracking and masks phone numbers in all log output.
"""

import logging
import re
from typing import Any, Optional

from config import CONFIG
from memory import find_contact_by_name

logger = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    """Return a masked phone number for safe logging (e.g. +91XXXXXX3210)."""
    clean = re.sub(r"\D", "", phone)
    if len(clean) >= 4:
        return "+" + "X" * (len(clean) - 4) + clean[-4:]
    return "XXXX"


def _sanitize_number(phone: str) -> str:
    """
    Normalize a phone number to E.164 format (e.g. +919876543210).

    Args:
        phone: Raw phone string from user or contacts.

    Returns:
        E.164-formatted phone number.

    Raises:
        ValueError if the number cannot be parsed.
    """
    phone = phone.strip()
    if not phone.startswith("+"):
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            return "+91" + digits
        elif len(digits) > 10:
            return "+" + digits
        raise ValueError(f"Cannot parse phone number: {phone}")
    return "+" + re.sub(r"\D", "", phone)


def _get_twilio_client():
    """
    Return an initialised Twilio REST client.

    Returns:
        twilio.rest.Client instance.

    Raises:
        ImportError if twilio package is not installed.
        RuntimeError if Twilio credentials are not configured.
    """
    if not CONFIG.has_twilio():
        raise RuntimeError("Twilio credentials not configured. Set TWILIO_* in .env")
    from twilio.rest import Client  # type: ignore[import]
    return Client(CONFIG.TWILIO_ACCOUNT_SID, CONFIG.TWILIO_AUTH_TOKEN)


async def _resolve_contact(contact: str) -> Optional[str]:
    """
    Resolve a contact name or raw number to a phone number.

    Args:
        contact: Name or phone number string.

    Returns:
        Phone number string, or None if contact not found by name.
    """
    # If it looks like a phone number, use directly
    if re.match(r"^[+\d\s\-()]+$", contact) and any(c.isdigit() for c in contact):
        return contact

    # Otherwise look up by name
    row = await find_contact_by_name(contact)
    if row:
        return row.get("phone")
    return None


async def make_call(contact: str) -> dict[str, Any]:
    """
    Initiate an outbound phone call via Twilio.

    The call plays a TwiML message that Jarvis has been requested to call.
    The TwiML URL is a simple public demo endpoint; in production replace with
    your own TwiML Bin URL.

    Args:
        contact: Contact name or phone number in any format.

    Returns:
        Dict with keys: success, call_sid (on success) or error (on failure).
    """
    if not CONFIG.has_twilio():
        return {
            "success": False,
            "error": "Twilio is not configured. Please set TWILIO_* credentials in .env",
            "code": "CONFIG_MISSING",
        }

    phone = await _resolve_contact(contact)
    if not phone:
        return {
            "success": False,
            "error": f"Contact '{contact}' not found. Please add them first.",
        }

    try:
        phone = _sanitize_number(phone)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    try:
        client = _get_twilio_client()
        call = client.calls.create(
            to=phone,
            from_=CONFIG.TWILIO_PHONE_NUMBER,
            twiml=(
                "<Response>"
                "<Say voice='alice'>Hello! This is Jarvis calling on behalf of your owner. "
                "The call was requested via the Jarvis AI assistant.</Say>"
                "</Response>"
            ),
        )
        logger.info("Call initiated to %s — SID: %s", _mask_phone(phone), call.sid)
        return {
            "success": True,
            "call_sid": call.sid,
            "to": _mask_phone(phone),
            "status": call.status,
        }
    except ImportError:
        return {"success": False, "error": "twilio package not installed."}
    except Exception as exc:
        logger.error("Twilio call failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def send_sms(contact: str, message: str) -> dict[str, Any]:
    """
    Send an SMS message via Twilio.

    Args:
        contact: Contact name or phone number.
        message: The SMS body text.

    Returns:
        Dict with keys: success, message_sid (on success) or error (on failure).
    """
    if not CONFIG.has_twilio():
        return {
            "success": False,
            "error": "Twilio is not configured.",
            "code": "CONFIG_MISSING",
        }

    phone = await _resolve_contact(contact)
    if not phone:
        return {
            "success": False,
            "error": f"Contact '{contact}' not found.",
        }

    try:
        phone = _sanitize_number(phone)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    # Truncate SMS to 160 chars for a single segment
    if len(message) > 1600:
        message = message[:1597] + "..."

    try:
        client = _get_twilio_client()
        msg = client.messages.create(
            to=phone,
            from_=CONFIG.TWILIO_PHONE_NUMBER,
            body=message,
        )
        logger.info("SMS sent to %s — SID: %s", _mask_phone(phone), msg.sid)
        return {
            "success": True,
            "message_sid": msg.sid,
            "to": _mask_phone(phone),
            "chars": len(message),
        }
    except ImportError:
        return {"success": False, "error": "twilio package not installed."}
    except Exception as exc:
        logger.error("Twilio SMS failed: %s", exc)
        return {"success": False, "error": str(exc)}
