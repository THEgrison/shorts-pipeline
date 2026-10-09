"""Decrypt account tokens and refresh when expired."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.db.enums import Platform
from shorts_pipeline.db.models import Account
from shorts_pipeline.logging_setup import get_logger
from shorts_pipeline.security import decrypt_token, encrypt_token

logger = get_logger(__name__)


def get_access_token(account: Account, settings: Settings | None = None) -> str:
    """Return a usable access token (refreshing Google tokens when needed)."""
    cfg = settings or get_settings()
    if not account.access_token_encrypted:
        return "dry-run-token"
    token = decrypt_token(account.access_token_encrypted, cfg)
    if account.token_expires_at and account.token_expires_at <= datetime.now(UTC) + timedelta(
        minutes=2
    ):
        refreshed = try_refresh(account, cfg)
        if refreshed:
            return refreshed
    return token


def try_refresh(account: Account, settings: Settings) -> str | None:
    """Refresh OAuth token when possible; updates encrypted fields in-memory."""
    if not account.refresh_token_encrypted:
        return None
    refresh = decrypt_token(account.refresh_token_encrypted, settings)
    try:
        if account.platform == Platform.YOUTUBE_SHORTS:
            return _refresh_google(account, refresh, settings)
        if account.platform == Platform.TIKTOK:
            return _refresh_tiktok(account, refresh, settings)
        # Meta long-lived tokens — best-effort stub
        logger.warning("tokens.refresh_unsupported", platform=account.platform.value)
        return None
    except Exception:
        logger.exception("tokens.refresh_failed", account_id=account.id)
        return None


def _refresh_google(account: Account, refresh_token: str, settings: Settings) -> str | None:
    client_id = settings.youtube_oauth_client_id
    client_secret = settings.youtube_oauth_client_secret
    if not client_id or not client_secret:
        return None
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id.get_secret_value(),
            "client_secret": client_secret.get_secret_value(),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    access = str(data["access_token"])
    account.access_token_encrypted = encrypt_token(access, settings)
    expires_in = int(data.get("expires_in", 3600))
    account.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return access


def _refresh_tiktok(account: Account, refresh_token: str, settings: Settings) -> str | None:
    key = settings.tiktok_client_key
    secret = settings.tiktok_client_secret
    if not key or not secret:
        return None
    resp = httpx.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": key.get_secret_value(),
            "client_secret": secret.get_secret_value(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    access = data.get("access_token") or (data.get("data") or {}).get("access_token")
    if not access:
        return None
    account.access_token_encrypted = encrypt_token(access, settings)
    return str(access)
