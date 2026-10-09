"""Dead-letter / failure alerts via Discord / Telegram / generic webhook."""

from __future__ import annotations

from typing import Any

import httpx

from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


def send_alert(
    message: str, *, settings: Settings | None = None, extra: dict[str, Any] | None = None
) -> bool:
    """Send an alert to configured webhooks. Returns True if at least one succeeded."""
    cfg = settings or get_settings()
    payload_extra = extra or {}
    sent = False

    if cfg.alert_discord_webhook_url:
        try:
            httpx.post(
                cfg.alert_discord_webhook_url,
                json={"content": f"🚨 **Shorts Pipeline**\n{message}"},
                timeout=10.0,
            ).raise_for_status()
            sent = True
        except Exception:
            logger.exception("alert.discord_failed")

    if cfg.alert_telegram_bot_token and cfg.alert_telegram_chat_id:
        try:
            token = cfg.alert_telegram_bot_token.get_secret_value()
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            httpx.post(
                url,
                json={"chat_id": cfg.alert_telegram_chat_id, "text": f"Shorts Pipeline\n{message}"},
                timeout=10.0,
            ).raise_for_status()
            sent = True
        except Exception:
            logger.exception("alert.telegram_failed")

    if cfg.alert_webhook_url:
        try:
            httpx.post(
                cfg.alert_webhook_url,
                json={"message": message, **payload_extra},
                timeout=10.0,
            ).raise_for_status()
            sent = True
        except Exception:
            logger.exception("alert.webhook_failed")

    if not sent:
        logger.warning("alert.no_channel_configured", message=message)
    return sent
