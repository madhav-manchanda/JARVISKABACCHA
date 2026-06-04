"""
auth.py — JWT authentication for the Jarvis API.
Single-user personal assistant — credentials stored in .env.
Uses python-jose for JWT tokens and passlib (bcrypt) for password hashing.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import CONFIG

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

ACCESS = "access"
REFRESH = "refresh"


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain: The raw password from the login request.
        hashed: The bcrypt hash stored in config.

    Returns:
        True if the password matches.
    """
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    """
    Hash a plain-text password with bcrypt.

    Args:
        password: The raw password to hash.

    Returns:
        Bcrypt hash string.
    """
    return pwd_context.hash(password)


def authenticate(username: str, password: str) -> bool:
    """
    Authenticate the single Jarvis user against .env credentials.
    Supports both bcrypt-hashed passwords (recommended) and plain-text
    passwords (development convenience — warns if used).

    Args:
        username: Username from the login request.
        password: Plain-text password from the login request.

    Returns:
        True if credentials are valid.
    """
    if username != CONFIG.JARVIS_USERNAME:
        return False

    stored = CONFIG.JARVIS_PASSWORD
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        return verify_password(password, stored)

    # Plain-text comparison (development only)
    logger.warning(
        "JARVIS_PASSWORD is plain text. Store a bcrypt hash in production: "
        "python -c \"from passlib.context import CryptContext; "
        "print(CryptContext(schemes=['bcrypt']).hash('yourpassword'))\""
    )
    return password == stored


def _make_token(subject: str, kind: str, delta: timedelta) -> str:
    """
    Create a signed JWT token.

    Args:
        subject: The username to encode.
        kind: Token type — 'access' or 'refresh'.
        delta: How long until the token expires.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": kind,
        "iat": now,
        "exp": now + delta,
    }
    return jwt.encode(payload, CONFIG.JWT_SECRET, algorithm=CONFIG.JWT_ALGORITHM)


def create_access_token(username: str) -> str:
    """
    Create a short-lived access token (default 30 minutes).

    Args:
        username: Authenticated user's username.

    Returns:
        Signed JWT access token.
    """
    return _make_token(
        username, ACCESS,
        timedelta(minutes=CONFIG.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(username: str) -> str:
    """
    Create a long-lived refresh token (default 7 days).

    Args:
        username: Authenticated user's username.

    Returns:
        Signed JWT refresh token.
    """
    return _make_token(
        username, REFRESH,
        timedelta(days=CONFIG.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_kind: str) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: Raw JWT string.
        expected_kind: Either 'access' or 'refresh'.

    Returns:
        Decoded payload dict.

    Raises:
        HTTPException 401 if token is expired, invalid, or the wrong type.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, CONFIG.JWT_SECRET, algorithms=[CONFIG.JWT_ALGORITHM]
        )
    except JWTError as e:
        logger.warning("JWT decode error: %s", e)
        raise exc from e

    if payload.get("type") != expected_kind:
        raise exc
    if payload.get("sub") != CONFIG.JARVIS_USERNAME:
        raise exc
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    FastAPI dependency — validates the Bearer access token on protected routes.

    Args:
        credentials: HTTPBearer credentials from Authorization header.

    Returns:
        The authenticated username string.

    Raises:
        HTTPException 401 on any authentication failure.
    """
    payload = decode_token(credentials.credentials, ACCESS)
    username: Optional[str] = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return username
