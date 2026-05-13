"""Azure resources inventory puller — AOAI, Foundry, AI Search, ML, Hosted Compute.

Uses ARM list endpoints under https://management.azure.com so we don't need
``azure-mgmt-*`` SDKs as hard dependencies; the docstring of each method
names the canonical SDK call for parity.

Output: ``AzureInventoryRow`` dicts. Idle-endpoint and AI Search rightsizing
detectors in :mod:`ai_finops.optimisation` consume this table.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from ._http import TokenProvider, request_with_retry
from .scopes import AZURE_MGMT, AZURE_MGMT_SCOPE

logger = logging.getLogger(__name__)

SOURCE = "azure_resource_manager"


class AzureInventoryPuller:
    """Enumerate Azure resources relevant to AI workloads."""

    source_system = SOURCE
    sdk_call = (
        "azure-mgmt-cognitiveservices: CognitiveServicesManagementClient.accounts.list, "
        "azure-mgmt-search: SearchManagementClient.services.list_by_subscription, "
        "azure-mgmt-machinelearningservices: AzureMachineLearningWorkspaces.workspaces.list_by_subscription"
    )

    # Resource provider list filter -> our normalised "kind"
    RESOURCE_TYPES = {
        "Microsoft.CognitiveServices/accounts": "cognitive_services",
        "Microsoft.Search/searchServices": "ai_search",
        "Microsoft.MachineLearningServices/workspaces": "ml_workspace",
        "Microsoft.App/containerApps": "container_app",
        "Microsoft.Web/sites": "app_service",
    }

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        subscription_id: str | None = None,
        api_version: str = "2021-04-01",
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._sub = subscription_id
        self._api_version = api_version

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None or not self._sub:
            return False
        try:
            url = (
                f"{AZURE_MGMT}/subscriptions/{self._sub}/resources"
                f"?$top=1&api-version={self._api_version}"
            )
            response = request_with_retry(
                self._client, "GET", url,
                headers=self._tokens.auth_header(AZURE_MGMT_SCOPE),
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Azure inventory probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    def fetch(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None or not self._sub:
            raise RuntimeError(
                "AzureInventoryPuller requires HTTP client + TokenProvider + subscription_id."
            )
        rt_filter = " or ".join(f"resourceType eq '{rt}'" for rt in self.RESOURCE_TYPES)
        url: str | None = (
            f"{AZURE_MGMT}/subscriptions/{self._sub}/resources"
            f"?$filter={rt_filter}&$expand=createdTime,changedTime,properties"
            f"&api-version={self._api_version}"
        )
        rows: list[dict[str, Any]] = []
        while url:
            response = request_with_retry(
                self._client, "GET", url,
                headers=self._tokens.auth_header(AZURE_MGMT_SCOPE),
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ARM list resources failed: {response.status_code} {response.text[:200]}"
                )
            data = response.json()
            rows.extend(data.get("value", []))
            url = data.get("nextLink")
        return rows

    # ------------------------------------------------------------------
    def normalise(self, resources: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        ts = datetime.now(UTC).replace(tzinfo=None)
        for r in resources:
            resource_id = str(r.get("id") or "")
            if not resource_id:
                continue
            rtype = str(r.get("type") or "")
            kind = self.RESOURCE_TYPES.get(rtype, "other")
            yield {
                "resource_id": resource_id,
                "captured_at": ts,
                "name": str(r.get("name") or ""),
                "kind": kind,
                "resource_type": rtype,
                "location": str(r.get("location") or ""),
                "sku_name": str((r.get("sku") or {}).get("name") or ""),
                "tags": ",".join(f"{k}={v}" for k, v in (r.get("tags") or {}).items())[:512],
                "subscription_id": self._sub or "",
                "source_system": SOURCE,
                "raw_record_id": resource_id,
            }
