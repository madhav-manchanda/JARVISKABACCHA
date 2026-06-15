"""
api/models/intent.py — Pydantic models for the intent JSON contract.
These models define the exact shape returned to clients (Web Dashboard).
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class IntentParams(BaseModel):
    """
    Flexible params dict for any action.
    Web Dashboard switches on 'action' and reads params accordingly.
    """
    model_config = {"extra": "allow"}


class Intent(BaseModel):
    """
    Structured intent returned by the brain.
    For device-side actions, the Web Dashboard reads this to execute locally.
    For server-side actions, this describes what the server did.
    """
    action: str = Field(..., description="Classified action name")
    app: Optional[str] = Field(None, description="App to open for device actions")
    params: dict[str, Any] = Field(default_factory=dict, description="All data needed to execute the action")
    confirmation_required: bool = Field(False, description="True for payments, messages, calls")
    confirmation_message: Optional[str] = Field(None, description="Spoken confirmation prompt")


class JarvisResponse(BaseModel):
    """
    The full response contract for POST /command/text and POST /command/voice.
    Designed so the Web app can plug in with zero backend changes.
    """
    success: bool
    session_id: str
    language: str = Field("en", description="Detected language code")
    transcribed_text: Optional[str] = Field(None, description="Whisper output (voice endpoint only)")
    response_text: str = Field("", description="Natural language response to speak/show")
    response_audio_url: Optional[str] = Field(None, description="URL to the TTS audio file")
    execution_target: str = Field("server", description="'server' or 'device'")
    intent: Optional[Intent] = Field(None, description="Structured intent for web execution")
    follow_up_actions: list[Intent] = Field(default_factory=list, description="Sequential actions to execute after primary intent")
    data: Optional[dict[str, Any]] = Field(None, description="Extra data from server-side actions")
    error: Optional[str] = None
    code: Optional[str] = None
