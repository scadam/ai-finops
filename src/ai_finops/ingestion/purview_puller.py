"""Microsoft Purview puller — sensitivity labels, DLP policies, classifications.

Combines two surfaces:

* **Compliance Graph** (``/security/labels`` and ``/security/dataLossPreventionPolicies``
  on ``graph.microsoft.com/beta``) — sensitivity label catalogue + DLP rules.
* **Purview Data Map** (``/datamap/api/atlas/v2/...`` on the Purview account
  endpoint) — classifications attached to specific data sources, used to gate
  the modeller.

The canonical SDKs are ``azure-purview-account`` + ``azure-purview-datamap``;
we use REST so we don't take a hard dependency on a preview SDK.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from ._http import TokenProvider, request_with_retry
from .scopes import GRAPH_BETA, GRAPH_SCOPE, PURVIEW_SCOPE

logger = logging.getLogger(__name__)

SOURCE = "purview_compliance_graph"
SOURCE_DATAMAP = "purview_datamap"


class PurviewPuller:
    """Read-only Purview client for label + classification ingestion."""

    source_system = SOURCE
    sdk_call = (
        "GET /beta/security/labels, "
        "GET /beta/security/dataLossPreventionPolicies, "
        "GET {purview-account}.purview.azure.net/datamap/api/atlas/v2/types/classifications"
    )

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        purview_account_endpoint: str | None = None,
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._purview_endpoint = purview_account_endpoint.rstrip("/") if purview_account_endpoint else None

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None:
            return False
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/security/labels?$top=1",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Purview probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    def fetch_sensitivity_labels(self) -> list[dict[str, Any]]:
        return self._page_graph(f"{GRAPH_BETA}/security/labels")

    def fetch_dlp_policies(self) -> list[dict[str, Any]]:
        try:
            return self._page_graph(f"{GRAPH_BETA}/security/dataLossPreventionPolicies")
        except RuntimeError as exc:
            logger.warning("DLP policies unavailable: %s", exc)
            return []

    def fetch_classifications(self) -> list[dict[str, Any]]:
        if not self._purview_endpoint or self._client is None or self._tokens is None:
            return []
        url = f"{self._purview_endpoint}/datamap/api/atlas/v2/types/typedefs/classification"
        try:
            response = request_with_retry(
                self._client,
                "GET",
                url,
                headers=self._tokens.auth_header(PURVIEW_SCOPE),
            )
            if response.status_code >= 400:
                logger.warning(
                    "Purview classifications failed: %s %s",
                    response.status_code, response.text[:200],
                )
                return []
            payload = response.json()
            return list(payload.get("classificationDefs") or payload.get("value") or [])
        except Exception as exc:
            logger.warning("Purview classifications unavailable: %s", exc)
            return []

    # ------------------------------------------------------------------
    def _page_graph(self, url: str) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("PurviewPuller requires HTTP client + TokenProvider.")
        rows: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            response = request_with_retry(
                self._client, "GET", next_url, headers=self._tokens.auth_header(GRAPH_SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Purview Graph call failed: {response.status_code} {response.text[:200]}"
                )
            data = response.json()
            rows.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
        return rows

    # ------------------------------------------------------------------
    def normalise_labels(
        self,
        labels: list[dict[str, Any]],
        dlp_policies: list[dict[str, Any]] | None = None,
        classifications: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Emit ``DataSensitivityLabelRow``-shaped dicts."""
        ts = datetime.now(UTC).replace(tzinfo=None)
        dlp_policies = dlp_policies or []
        classifications = classifications or []
        for label in labels:
            label_id = str(label.get("id") or label.get("name") or "")
            if not label_id:
                continue
            sensitivity = str(label.get("sensitivity") or label.get("name") or "internal").lower()
            yield {
                "label_id": label_id,
                "captured_at": ts,
                "display_name": str(label.get("displayName") or label.get("name") or label_id),
                "sensitivity": sensitivity,
                "tooltip": str(label.get("tooltip") or label.get("description") or ""),
                "is_default": bool(label.get("isDefault")),
                "dlp_policy_count": sum(
                    1 for p in dlp_policies if label_id in (p.get("appliedLabels") or [])
                ),
                "classification_count": len(classifications),
                "source_system": SOURCE,
                "raw_record_id": label_id,
            }
