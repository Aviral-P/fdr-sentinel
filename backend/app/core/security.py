"""Password hashing and short-lived signed access-token helpers."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings
from app.core.errors import AppError

password_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def get_signing_key(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    key = settings.jwt_secret_key.get_secret_value()
    placeholder_values = {
        "replace_with_a_random_local_secret_of_at_least_32_characters",
        "changeme",
        "change-me",
        "secret",
        "your-secret-key",
    }
    if len(key.encode("utf-8")) < 32 or key.strip().lower() in placeholder_values:
        raise AppError(
            status_code=503,
            code="auth_not_configured",
            message="Authentication is not configured. Set JWT_SECRET_KEY to a unique random secret of at least 32 bytes; the documented placeholder is not accepted.",
        )
    return key


def create_access_token(user_id: str, settings: Settings | None = None) -> tuple[str, str, datetime]:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_minutes)
    token_id = str(uuid4())
    payload = {
        "sub": user_id,
        "jti": token_id,
        "iat": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
    }
    token = jwt.encode(payload, get_signing_key(settings), algorithm=JWT_ALGORITHM)
    return token, token_id, expires_at
