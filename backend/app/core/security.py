from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _create_token(sub: str, role: str, typ: TokenType, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "typ": typ,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str | int, role: str) -> str:
    return _create_token(
        str(sub), role, "access", timedelta(minutes=settings.access_token_ttl_minutes)
    )


def create_refresh_token(sub: str | int, role: str) -> str:
    return _create_token(
        str(sub), role, "refresh", timedelta(days=settings.refresh_token_ttl_days)
    )


def decode_token(token: str, expected_typ: TokenType) -> dict:
    """Decode and validate a JWT, raising 401 on any failure.

    Checks signature, expiry, and that the token's `typ` claim matches
    `expected_typ` so a refresh token cannot be used where an access
    token is required (and vice versa).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise credentials_exception from None

    if payload.get("typ") != expected_typ:
        raise credentials_exception
    if not payload.get("sub"):
        raise credentials_exception
    return payload
