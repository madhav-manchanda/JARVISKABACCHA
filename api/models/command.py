"""
api/models/command.py — Pydantic request models for command endpoints.
"""

import uuid
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TextCommandRequest(BaseModel):
    """Request body for POST /command/text."""
    text: str = Field(..., min_length=1, max_length=2000, description="The user's command text")
    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Session identifier — generated automatically if not provided",
    )
    deep_search: bool = Field(False, description="Flag to enable God-Mode deep searching")

    @field_validator("text")
    @classmethod
    def sanitise_text(cls, v: str) -> str:
        """Strip leading/trailing whitespace from input text."""
        return v.strip()


class ConfirmRequest(BaseModel):
    """Request body for POST /command/confirm."""
    session_id: str = Field(..., description="The session with the pending intent")
    confirmed: bool = Field(..., description="True if user confirmed, False if cancelled")
    intent_id: Optional[str] = Field(None, description="Optional intent tracking ID")
    # For dork confirmation, include the pending dork query
    dork_query: Optional[str] = Field(None, description="Dork query to execute (for dork confirmations)")
    # For dangerous download confirmation
    download_url: Optional[str] = Field(None, description="URL to download (for dangerous file confirmations)")
