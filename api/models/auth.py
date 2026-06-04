"""
api/models/auth.py — Pydantic models for authentication endpoints.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    """Response body for POST /auth/login and POST /auth/refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh."""
    refresh_token: str


class ContactCreate(BaseModel):
    """Request body for POST /contacts."""
    name: str = Field(..., min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=20)
    whatsapp: bool = False
    upi_id: str | None = Field(None, max_length=100, description="UPI ID e.g. rahul@okaxis")


class ContactUpdate(BaseModel):
    """Request body for PUT /contacts/{id}."""
    name: str | None = Field(None, min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=20)
    whatsapp: bool | None = None
    upi_id: str | None = Field(None, max_length=100)


class FactCreate(BaseModel):
    """Request body for POST /memory/facts."""
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1, max_length=2000)
