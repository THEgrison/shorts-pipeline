"""Settings and security helpers."""

from __future__ import annotations

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.security import decrypt_token, encrypt_token, generate_fernet_key


def test_settings_defaults(settings: Settings) -> None:
    assert settings.dry_run is True
    assert settings.app_env == "test"
    assert "fr" in settings.allowed_languages_list


def test_get_settings_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_token_roundtrip(settings: Settings) -> None:
    cipher = encrypt_token("oauth-secret-token", settings)
    assert cipher != "oauth-secret-token"
    assert decrypt_token(cipher, settings) == "oauth-secret-token"


def test_generate_fernet_key() -> None:
    key = generate_fernet_key()
    assert len(key) >= 32
