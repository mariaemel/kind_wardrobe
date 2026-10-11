import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

BCRYPT_MAX_PASSWORD_BYTES = 72


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Пароль слишком длинный")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


def create_token(subject: uuid.UUID, token_type: TokenType, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    if token_type is TokenType.ACCESS:
        expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(subject: uuid.UUID) -> tuple[str, str, str, datetime]:
    refresh_jti = uuid.uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    access_token = create_token(subject, TokenType.ACCESS)
    refresh_token = create_token(subject, TokenType.REFRESH, extra_claims={"jti": refresh_jti})
    return access_token, refresh_token, refresh_jti, expires_at


def decode_token_payload(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError
    if "sub" not in payload or "jti" not in payload:
        raise InvalidTokenError
    try:
        uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError from exc
    return payload


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    payload = decode_token_payload(token, expected_type)
    return uuid.UUID(payload["sub"])
