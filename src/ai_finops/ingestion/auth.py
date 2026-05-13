"""Single auth factory for every Microsoft SDK / REST puller.

Wraps :class:`azure.identity.DefaultAzureCredential` so the same code path
works for:

* **Managed Identity** in App Service / Functions (production).
* **Workload Identity Federation** in CI (GitHub Actions OIDC).
* ``az login`` device-code flow for local development.
* Static client-id / secret for unit tests via ``ClientSecretCredential``.

Every puller takes a :class:`MicrosoftAuthFactory` (or a TokenProvider it
returns) so we never re-instantiate credentials and tokens are cached per
scope inside :class:`~ai_finops.ingestion._http.TokenProvider`.
"""
from __future__ import annotations

import logging
from typing import Any

from ._http import TokenProvider

logger = logging.getLogger(__name__)


class MicrosoftAuthFactory:
    """Lazily build credentials and per-scope ``TokenProvider`` instances."""

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        credential: Any | None = None,
    ) -> None:
        self._tenant_id = tenant_id or None
        self._client_id = client_id or None
        self._client_secret = client_secret or None
        self._credential = credential
        self._providers: dict[str, TokenProvider] = {}

    # ------------------------------------------------------------------
    @property
    def credential(self) -> Any | None:
        if self._credential is not None:
            return self._credential
        try:
            if self._client_id and self._client_secret and self._tenant_id:
                from azure.identity import ClientSecretCredential

                self._credential = ClientSecretCredential(
                    tenant_id=self._tenant_id,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )
            else:
                from azure.identity import DefaultAzureCredential

                # ``managed_identity_client_id`` lets a User-Assigned MI be
                # selected when both system- and user-assigned identities
                # are attached (common in App Service).
                kwargs: dict[str, Any] = {}
                if self._client_id:
                    kwargs["managed_identity_client_id"] = self._client_id
                self._credential = DefaultAzureCredential(**kwargs)
        except Exception as exc:  # pragma: no cover - optional dep
            logger.warning("azure-identity not available: %s", exc)
            self._credential = None
        return self._credential

    # ------------------------------------------------------------------
    def token_provider(self) -> TokenProvider:
        """Return a TokenProvider that caches tokens per scope tuple."""
        key = "default"
        provider = self._providers.get(key)
        if provider is None:
            provider = TokenProvider(self.credential)
            self._providers[key] = provider
        return provider

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Return True iff a credential could be constructed.

        Used by ``GET /api/v1/data-sources`` to colour the puller status
        before it even attempts a remote call.
        """
        return self.credential is not None
