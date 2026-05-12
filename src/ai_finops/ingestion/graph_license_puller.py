"""Microsoft Graph — license + active-user puller."""
from __future__ import annotations

import csv
import io
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

# Approx per-seat monthly USD; only used as a fallback if a SKU lacks pricing
# in our rate cards. Per spec, this MUST be overridden by per_seat.yaml.
DEFAULT_SEAT_PRICE = Decimal("30")


class GraphLicensePuller:
    """Pull subscribed SKUs and active-user counts from Graph."""

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        seat_prices: dict[str, Decimal] | None = None,
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._seat_prices = seat_prices or {}

    # ------------------------------------------------------------------
    def fetch_skus(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("GraphLicensePuller requires HTTP client + TokenProvider.")
        url = f"{GRAPH_BASE}/subscribedSkus"
        skus: list[dict[str, Any]] = []
        while url:
            response = request_with_retry(
                self._client, "GET", url, headers=self._tokens.auth_header(SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Graph subscribedSkus failed: {response.status_code} {response.text[:200]}"
                )
            data = response.json()
            skus.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return skus

    def fetch_active_user_counts(self, period: str = "D7") -> dict[str, int]:
        """Return {sku_part_number: active_count}. Parses CSV body, falls back to JSON."""
        if self._client is None or self._tokens is None:
            raise RuntimeError("GraphLicensePuller requires HTTP client + TokenProvider.")
        url = f"{GRAPH_BASE}/reports/getOffice365ActiveUserDetail(period='{period}')"
        response = request_with_retry(
            self._client, "GET", url, headers=self._tokens.auth_header(SCOPE)
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Graph active users failed: {response.status_code} {response.text[:200]}"
            )
        body = response.text or ""
        return self._parse_active_users(body)

    @staticmethod
    def _parse_active_users(body: str) -> dict[str, int]:
        body = body.strip()
        if not body:
            return {}
        if body.startswith("{"):
            try:
                import json

                data = json.loads(body)
                value = data.get("value", data)
                if isinstance(value, dict):
                    return {str(k): int(v) for k, v in value.items()}
                if isinstance(value, list):
                    out: dict[str, int] = {}
                    for entry in value:
                        sku = entry.get("skuPartNumber") or entry.get("productName")
                        cnt = entry.get("activeUsers") or entry.get("activeUserCount") or 0
                        if sku:
                            out[str(sku)] = int(cnt)
                    return out
            except Exception:
                logger.warning("Could not parse JSON active-user body; ignoring")
                return {}
        try:
            reader = csv.DictReader(io.StringIO(body))
            counts: dict[str, int] = {}
            for row in reader:
                sku = row.get("Product") or row.get("SKU") or row.get("Service")
                active_raw = row.get("ActiveUsers") or row.get("Active Users") or "0"
                if sku:
                    try:
                        counts[str(sku)] = int(active_raw or 0)
                    except ValueError:
                        continue
            return counts
        except Exception as exc:
            logger.warning("CSV parse failed for active-user body: %s", exc)
            return {}

    # ------------------------------------------------------------------
    def normalise(
        self, skus: list[dict[str, Any]], active_counts: dict[str, int] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield CostEventRow-shaped dicts for relevant SKUs."""
        active_counts = active_counts or {}
        ts = datetime.now(UTC)
        for sku in skus:
            part_number = str(sku.get("skuPartNumber") or sku.get("partNumber") or "").lower()
            if not part_number:
                continue
            if "copilot" not in part_number and "m365_e" not in part_number:
                continue
            assigned = int(
                sku.get("consumedUnits") or sku.get("assignedUnits") or 0
            )
            active = int(active_counts.get(part_number, active_counts.get(part_number.upper(), 0)))
            price = self._seat_prices.get(part_number, DEFAULT_SEAT_PRICE)
            yield {
                "id": f"lic-{uuid.uuid4().hex[:16]}",
                "timestamp": ts,
                "meter": Meter.PER_SEAT.value,
                "agent_id": "",
                "agent_name": part_number,
                "agent_type": AgentType.DECLARATIVE_INSTRUCTION.value,
                "channel": Channel.M365_COPILOT.value,
                "user_license_type": UserLicenseType.M365_COPILOT_LICENSED.value,
                "sku_id": part_number,
                "assigned_users": assigned,
                "active_users_7d": active,
                "cost_actual_usd": (Decimal(assigned) * price),
                "source_system": "graph_license_api",
            }
