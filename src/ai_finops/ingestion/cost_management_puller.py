"""Azure Cost Management puller — replaces ad-hoc FOCUS CSV uploads.

Calls the Cost Management Query API
(``Microsoft.CostManagement/query``) and feeds the results through the
existing :class:`~ai_finops.ingestion.azure_focus_importer.FocusImporter`
so all downstream code paths stay identical to the CSV import flow.

Canonical SDK: ``azure-mgmt-costmanagement``
(``CostManagementClient.query.usage``).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ._http import TokenProvider, request_with_retry
from .azure_focus_importer import FocusImporter, FocusRowAdapter
from .scopes import AZURE_MGMT, AZURE_MGMT_SCOPE

logger = logging.getLogger(__name__)

SOURCE = "azure_cost_management_api"
QUERY_API_VERSION = "2023-11-01"


class CostManagementPuller:
    """Pull FOCUS-shaped cost data and feed FocusImporter directly."""

    source_system = SOURCE
    sdk_call = (
        "POST /providers/Microsoft.CostManagement/query "
        "(azure-mgmt-costmanagement: CostManagementClient.query.usage)"
    )

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        scope: str | None = None,
    ) -> None:
        """``scope`` is e.g. ``subscriptions/{sub_id}`` or
        ``subscriptions/{sub_id}/resourceGroups/{rg}``."""
        self._tokens = token_provider
        self._client = client
        self._scope = scope.strip("/") if scope else None

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None or not self._scope:
            return False
        try:
            url = (
                f"{AZURE_MGMT}/{self._scope}/providers/Microsoft.CostManagement/"
                f"query?api-version={QUERY_API_VERSION}"
            )
            # A trivial probe: tiny dataset request.
            body = self._build_query(days=1)
            response = request_with_retry(
                self._client, "POST", url,
                json=body,
                headers={
                    **self._tokens.auth_header(AZURE_MGMT_SCOPE),
                    "Content-Type": "application/json",
                },
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Cost Management probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    @staticmethod
    def _build_query(days: int = 30) -> dict[str, Any]:
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        return {
            "type": "ActualCost",
            "dataSet": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {"name": "Cost", "function": "Sum"},
                    "usageQuantity": {"name": "UsageQuantity", "function": "Sum"},
                },
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "ResourceId"},
                    {"type": "TagKey", "name": "AgentId"},
                    {"type": "TagKey", "name": "CostCenter"},
                    {"type": "TagKey", "name": "Owner"},
                    {"type": "TagKey", "name": "Environment"},
                ],
            },
            "timeframe": "Custom",
            "timePeriod": {
                "from": start.strftime("%Y-%m-%dT00:00:00Z"),
                "to": end.strftime("%Y-%m-%dT23:59:59Z"),
            },
        }

    # ------------------------------------------------------------------
    def fetch(self, days: int = 30) -> list[FocusRowAdapter]:
        """Run the query and return FocusRowAdapter rows ready for FocusImporter."""
        if self._client is None or self._tokens is None or not self._scope:
            raise RuntimeError(
                "CostManagementPuller requires HTTP client + TokenProvider + scope."
            )
        url = (
            f"{AZURE_MGMT}/{self._scope}/providers/Microsoft.CostManagement/"
            f"query?api-version={QUERY_API_VERSION}"
        )
        body = self._build_query(days=days)
        adapters: list[FocusRowAdapter] = []
        next_link: str | None = url
        while next_link:
            response = request_with_retry(
                self._client, "POST", next_link,
                json=body,
                headers={
                    **self._tokens.auth_header(AZURE_MGMT_SCOPE),
                    "Content-Type": "application/json",
                },
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Cost Management query failed: {response.status_code} {response.text[:200]}"
                )
            payload = response.json()
            adapters.extend(self._adapters_from_payload(payload))
            next_link = (payload.get("properties") or {}).get("nextLink")
            # Body is repeated for paged calls.
        return adapters

    # ------------------------------------------------------------------
    @staticmethod
    def _adapters_from_payload(payload: dict[str, Any]) -> Iterator[FocusRowAdapter]:
        """Translate Cost Management columnar response → FOCUS-shaped rows."""
        props = payload.get("properties") or {}
        columns = [str(c.get("name") or "") for c in (props.get("columns") or [])]
        rows = props.get("rows") or []
        for raw in rows:
            mapping = dict(zip(columns, raw, strict=False))
            cost = mapping.get("Cost") or 0
            usage_qty = mapping.get("UsageQuantity") or 0
            service = str(mapping.get("ServiceName") or "")
            resource_id = str(mapping.get("ResourceId") or "")
            usage_date = str(mapping.get("UsageDate") or mapping.get("BillingPeriod") or "")
            yield FocusRowAdapter({
                "BillingPeriodStart": usage_date[:10] if usage_date else "",
                "ChargePeriodStart": usage_date,
                "BilledCost": cost,
                "EffectiveCost": cost,
                "ServiceName": service,
                "ServiceCategory": "AI and Machine Learning",
                "ResourceId": resource_id,
                "ResourceName": resource_id.rsplit("/", 1)[-1] if resource_id else "",
                "ResourceType": "",
                "Tags.AgentId": str(mapping.get("AgentId") or ""),
                "Tags.CostCenter": str(mapping.get("CostCenter") or ""),
                "Tags.Owner": str(mapping.get("Owner") or ""),
                "Tags.Environment": str(mapping.get("Environment") or ""),
                "UsageQuantity": usage_qty,
                "UsageUnit": str(mapping.get("UnitOfMeasure") or ""),
            })

    # ------------------------------------------------------------------
    def into_importer(self, importer: FocusImporter | None = None) -> tuple[FocusImporter, list[FocusRowAdapter]]:
        """Convenience: build a FocusImporter pre-loaded with our rows."""
        importer = importer or FocusImporter(source_system=SOURCE)
        return importer, self.fetch()
