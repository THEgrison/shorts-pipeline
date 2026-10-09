"""Shared HTTP client utilities."""

from __future__ import annotations

import time
from threading import Lock

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Simple token-bucket style rate limiter (thread-safe)."""

    def __init__(self, *, max_calls: int, period_seconds: float) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._timestamps: list[float] = []
        self._lock = Lock()

    def acquire(self) -> None:
        """Block until a call slot is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self.period_seconds]
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                sleep_for = self.period_seconds - (now - self._timestamps[0])
            time.sleep(max(sleep_for, 0.01))


class BaseHttpClient:
    """HTTP client with timeout, retries, and optional rate limiting."""

    def __init__(
        self,
        *,
        base_url: str = "",
        timeout: float = 30.0,
        rate_limiter: RateLimiter | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limiter = rate_limiter
        self._headers = headers or {}
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._headers,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseHttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool | None] | None = None,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Perform an HTTP request with retries on transport errors."""
        if self.rate_limiter:
            self.rate_limiter.acquire()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        logger.debug("http.request", method=method, url=url)
        response = self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers=headers,
        )
        response.raise_for_status()
        return response
