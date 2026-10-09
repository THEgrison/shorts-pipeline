"""Anthropic Claude API client for structured JSON outputs."""

from __future__ import annotations

import json
from typing import Any

import httpx

from shorts_pipeline.clients.base import BaseHttpClient, RateLimiter
from shorts_pipeline.config import Settings, get_settings
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class AnthropicClient(BaseHttpClient):
    """Minimal Messages API wrapper."""

    def __init__(
        self,
        *,
        api_key: str,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.api_key = api_key
        self.settings = cfg
        self.model = cfg.anthropic_model
        self.base_url = "https://api.anthropic.com"
        self.timeout = 120.0
        self.rate_limiter = RateLimiter(max_calls=20, period_seconds=60.0)
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._headers,
            transport=transport,
            follow_redirects=True,
        )

    def create_message(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> str:
        """Return assistant text content."""
        if self.rate_limiter:
            self.rate_limiter.acquire()
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        logger.debug("anthropic.request", model=self.model)
        response = self._client.post("/v1/messages", json=payload)
        response.raise_for_status()
        data = response.json()
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        return "\n".join(texts).strip()

    def create_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> Any:
        """Ask for JSON and parse it (strips markdown fences if present)."""
        text = self.create_message(system=system, user=user, max_tokens=max_tokens)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # drop first and last fence lines
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)
