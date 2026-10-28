"""Configuration safety checks for signing keys."""

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import get_signing_key


def test_signing_key_rejects_documented_placeholder():
    settings = Settings(_env_file=None, jwt_secret_key=SecretStr("replace_with_a_random_local_secret_of_at_least_32_characters"))
    with pytest.raises(AppError) as exc:
        get_signing_key(settings)
    assert exc.value.code == "auth_not_configured"


def test_signing_key_accepts_unique_random_looking_key():
    key = "test-only-unique-random-signing-key-0123456789"
    settings = Settings(_env_file=None, jwt_secret_key=SecretStr(key))
    assert get_signing_key(settings) == key
