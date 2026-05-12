"""HTTP utilities used by ingestion connectors.

Provides a token provider abstraction (so tests can stub credentials)
and a retry helper that respects ``Retry-After`` for 429/5xx.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class _CredentialProtocol(Protocol):
    def get_token(self, *scopes: str) -> Any:  # pragma: no cover - protocol
        ...


class TokenProvider:
    """Wrap any object with ``get_token(*scopes)`` and cache tokens per scope."""

    def __init__(self, credential: _CredentialProtocol | None = None) -> None:
        if credential is None:
            try:
                from azure.identity import DefaultAzureCredential

                credential = DefaultAzureCredential()
            except Exception:  # pragma: no cover - optional dep
                credential = None
        self._credential = credential
        self._cache: dict[tuple[str, ...], tuple[str, float]] = {}

    def get(self, *scopes: str) -> str:
        if self._credential is None:
            raise RuntimeError("No credential configured for TokenProvider.")
        cached = self._cache.get(scopes)
        now = time.time()
        if cached and cached[1] - 60 > now:
            return cached[0]
        token = self._credential.get_token(*scopes)
        token_str = getattr(token, "token", None) or str(token)
        expires = getattr(token, "expires_on", now + 3000)
        self._cache[scopes] = (token_str, float(expires))
        return token_str

    def auth_header(self, *scopes: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get(*scopes)}"}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request with exponential backoff on 429/5xx errors."""
    attempt = 0
    while True:
        attempt += 1
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt >= max_attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            logger.warning("HTTP transport error (%s); retrying in %.1fs", exc, delay)
            time.sleep(delay)
            continue
        if response.status_code < 400 or response.status_code not in {429, 500, 502, 503, 504}:
            return response
        if attempt >= max_attempts:
            return response
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = base_delay * (2 ** (attempt - 1))
        else:
            delay = base_delay * (2 ** (attempt - 1)) + random.random()  # noqa: S311
        delay = min(max_delay, delay)
        logger.warning(
            "HTTP %s for %s; retry %d/%d in %.1fs",
            response.status_code, url, attempt, max_attempts, delay,
        )
        time.sleep(delay)
