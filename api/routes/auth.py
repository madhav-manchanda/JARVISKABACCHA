"""
api/routes/auth.py — Authentication endpoints.
Provides token generation and refresh functionality.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Any

from auth import authenticate, create_access_token, create_refresh_token, decode_token, REFRESH
from api.models.auth import LoginRequest, TokenResponse, RefreshRequest
from config import CONFIG

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> Any:
    """
    Authenticate and return access + refresh tokens.
    """
    if not authenticate(req.username, req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(req.username),
        refresh_token=create_refresh_token(req.username),
        expires_in_seconds=CONFIG.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> Any:
    """
    Issue a new access token using a valid refresh token.
    """
    payload = decode_token(req.refresh_token, REFRESH)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    return TokenResponse(
        access_token=create_access_token(username),
        refresh_token=req.refresh_token,  # Keep the same refresh token
        expires_in_seconds=CONFIG.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
