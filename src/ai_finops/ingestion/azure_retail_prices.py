"""Azure Retail Prices refresher.

Fetches the public retail prices catalogue and diffs it against the local
rate card. Differences over a configurable threshold are reported.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from ._http import request_with_retry

logger = logging.getLogger(__name__)

PRICES_URL = "https://prices.azure.com/api/retail/prices"


@dataclass
class PriceDiff:
    sku_id: str
    meter_name: str
    local_price: Decimal
    remote_price: Decimal
    delta_pct: Decimal


@dataclass
class RefreshResult:
    fetched: int = 0
    diffs: list[PriceDiff] = field(default_factory=list)


class RetailPricesRefresher:
    """Fetch + diff Azure retail prices."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        threshold_pct: Decimal = Decimal("5"),
    ) -> None:
        self._client = client
        self._threshold = threshold_pct

    def fetch(self, filter_query: str | None = None) -> Iterator[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("RetailPricesRefresher.fetch() requires an HTTP client.")
        params: dict[str, Any] = {}
        if filter_query:
            params["$filter"] = filter_query
        url = PRICES_URL
        first = True
        while url:
            response = request_with_retry(
                self._client,
                "GET",
                url,
                params=params if first else None,
            )
            first = False
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Retail prices fetch failed: {response.status_code} {response.text[:200]}"
                )
            payload = response.json()
            yield from payload.get("Items", [])
            url = payload.get("NextPageLink") or ""

    def diff_against_local(
        self,
        remote_items: Iterable[dict[str, Any]],
        local_prices: dict[str, Decimal],
    ) -> RefreshResult:
        result = RefreshResult()
        for item in remote_items:
            result.fetched += 1
            sku = str(item.get("skuId") or item.get("meterId") or "")
            meter = str(item.get("meterName") or "")
            try:
                remote_price = Decimal(str(item.get("retailPrice") or item.get("unitPrice") or 0))
            except Exception:
                continue
            local = local_prices.get(sku) or local_prices.get(meter)
            if local is None or local == 0:
                continue
            delta = ((remote_price - local) / local) * Decimal("100")
            if abs(delta) >= self._threshold:
                result.diffs.append(
                    PriceDiff(
                        sku_id=sku,
                        meter_name=meter,
                        local_price=local,
                        remote_price=remote_price,
                        delta_pct=delta,
                    )
                )
        return result
