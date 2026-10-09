"""Token encryption helpers (Fernet)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def _fernet(settings: Settings | None = None) -> Fernet:
    cfg = settings or get_settings()
    key = cfg.fernet_key.get_secret_value().encode("utf-8")
    # Accept raw 32-byte url-safe base64 keys; if invalid, derive a stable test key
    try:
        return Fernet(key)
    except (ValueError, InvalidToken):
        # Development fallback: derive from secret_key (NOT for production)
        import base64
        import hashlib

        digest = hashlib.sha256(cfg.secret_key.get_secret_value().encode()).digest()
        derived = base64.urlsafe_b64encode(digest)
        logger.warning("fernet_key_invalid_using_derived_fallback")
        return Fernet(derived)


def encrypt_token(plaintext: str, settings: Settings | None = None) -> str:
    """Encrypt an OAuth token for storage."""
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str, settings: Settings | None = None) -> str:
    """Decrypt a stored OAuth token."""
    return _fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def generate_fernet_key() -> str:
    """Generate a new Fernet key (for .env setup)."""
    return Fernet.generate_key().decode("utf-8")
