"""Microsoft Graph — Copilot Credits usage report puller."""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from ..domain.enums import AgentType, Channel, Meter, UserLicenseType
from ._http import TokenProvider, request_with_retry

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/.default"


class GraphCreditsPuller:
    """Pull the Copilot Credits usage report from Graph."""

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        period: str = "D30",
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._period = period

    # ------------------------------------------------------------------
    def fetch(self) -> list[dict[str, Any]]:
        """Return raw rows from Graph (list of dicts)."""
        if self._client is None or self._tokens is None:
            raise RuntimeError(
                "GraphCreditsPuller.fetch() requires both an HTTP client and TokenProvider."
            )
        url = (
            f"{GRAPH_BASE}/reports/getMicrosoftCopilotUsageReport(period='{self._period}')"
        )
        rows: list[dict[str, Any]] = []
        while url:
            response = request_with_retry(
                self._client, "GET", url, headers=self._tokens.auth_header(SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Graph credits report failed: {response.status_code} {response.text[:200]}"
                )
            payload = response.json()
            rows.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
        return rows

    # ------------------------------------------------------------------
    def normalise(self, rows: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield ``CostEventRow``-shaped dicts for each raw row."""
        payg_rate = Decimal("0.01")
        for row in rows:
            credits_used = int(row.get("creditsUsed") or row.get("credits") or 0)
            shadow = int(row.get("shadowCredits") or row.get("creditsShadow") or 0)
            zero_rated = bool(row.get("isZeroRated"))
            consumed = 0 if zero_rated else credits_used
            agent_id = str(row.get("agentId") or row.get("agent_id") or "")
            agent_name = str(row.get("agentName") or row.get("agent_name") or agent_id)
            ts_raw = row.get("reportDate") or row.get("usageDate") or datetime.now(UTC).isoformat()
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(UTC)
            yield {
                "id": f"cc-{uuid.uuid4().hex[:16]}",
                "timestamp": ts,
                "meter": Meter.COPILOT_CREDITS.value,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_type": AgentType.COPILOT_STUDIO_CUSTOM.value,
                "channel": Channel.M365_COPILOT.value,
                "user_license_type": (
                    UserLicenseType.M365_COPILOT_LICENSED.value
                    if zero_rated
                    else UserLicenseType.INTERNAL_UNLICENSED.value
                ),
                "credits_consumed": consumed,
                "credits_shadow": shadow if zero_rated else 0,
                "b2e_zero_rated": zero_rated,
                "cost_actual_usd": (Decimal(consumed) * payg_rate),
                "source_system": "graph_credits_report",
                "raw_record_id": str(row.get("id") or row.get("recordId") or ""),
            }
