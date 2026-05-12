"""Azure FOCUS 1.1 export importer.

Reads CSV in FOCUS schema, classifies AI-related rows, splits into tagged /
untagged groups, and yields cost-event-shaped dicts.
"""
from __future__ import annotations

import csv
import logging
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TextIO

from ..domain.enums import AgentType, Channel, Meter, UserLicenseType

logger = logging.getLogger(__name__)

REQUIRED_TAGS = ("AgentId", "CostCenter", "Owner", "Environment")

# Maps a lowercase token found in ServiceName to an azure_service tag.
SERVICE_KEYWORDS: list[tuple[str, str]] = [
    ("openai", "azure_openai"),
    ("cognitive services", "azure_openai"),
    ("search", "ai_search"),
    ("foundry", "foundry_tools"),
    ("functions", "functions"),
    ("logic apps", "logic_apps"),
    ("storage", "storage"),
    ("application insights", "application_insights"),
]


def _to_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_ts(value: Any) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)


@dataclass
class FocusRowAdapter:
    """Light wrapper around a FOCUS CSV row."""

    row: dict[str, Any]

    @property
    def service_name(self) -> str:
        return str(self.row.get("ServiceName", "") or "").strip()

    @property
    def billed_cost(self) -> Decimal:
        return _to_decimal(self.row.get("BilledCost"))

    @property
    def effective_cost(self) -> Decimal:
        return _to_decimal(self.row.get("EffectiveCost"))

    @property
    def usage_quantity(self) -> Decimal:
        return _to_decimal(self.row.get("UsageQuantity"))

    @property
    def tags(self) -> dict[str, str]:
        return {key: str(self.row.get(f"Tags.{key}", "") or "").strip() for key in REQUIRED_TAGS}

    def is_ai_related(self) -> bool:
        name = self.service_name.lower()
        return any(token in name for token in (k for k, _ in SERVICE_KEYWORDS))

    def detect_meter(self) -> str:
        return Meter.AZURE_CONSUMPTION.value

    def detect_azure_service(self) -> str:
        name = self.service_name.lower()
        for token, svc in SERVICE_KEYWORDS:
            if token in name:
                return svc
        return "azure_other"

    def has_required_tags(self) -> bool:
        tags = self.tags
        return all(tags.get(k) for k in REQUIRED_TAGS)


class FocusImporter:
    """Parse FOCUS CSV files."""

    def __init__(self, source_system: str = "azure_focus_export") -> None:
        self._source_system = source_system

    def parse(self, source: TextIO | Iterable[dict[str, Any]]) -> list[FocusRowAdapter]:
        if hasattr(source, "read"):
            reader = csv.DictReader(source)
            return [FocusRowAdapter(row) for row in reader]
        return [FocusRowAdapter(dict(row)) for row in source]

    def split_tagged(
        self, rows: list[FocusRowAdapter]
    ) -> tuple[list[FocusRowAdapter], list[FocusRowAdapter]]:
        tagged: list[FocusRowAdapter] = []
        untagged: list[FocusRowAdapter] = []
        for r in rows:
            if not r.is_ai_related():
                continue
            (tagged if r.has_required_tags() else untagged).append(r)
        return tagged, untagged

    def to_cost_events(self, rows: list[FocusRowAdapter]) -> Iterator[dict[str, Any]]:
        for r in rows:
            tags = r.tags
            yield {
                "id": f"focus-{uuid.uuid4().hex[:16]}",
                "timestamp": _parse_ts(r.row.get("ChargePeriodStart")),
                "meter": r.detect_meter(),
                "agent_id": tags["AgentId"],
                "agent_name": tags["AgentId"],
                "agent_type": AgentType.HYBRID_STUDIO_FOUNDRY.value,
                "channel": Channel.CUSTOM_CHANNEL.value,
                "user_license_type": UserLicenseType.INTERNAL_UNLICENSED.value,
                "cost_center": tags["CostCenter"],
                "owner": tags["Owner"],
                "environment": tags["Environment"],
                "azure_service": r.detect_azure_service(),
                "azure_resource_id": str(r.row.get("ResourceId") or ""),
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_actual_usd": r.effective_cost,
                "source_system": self._source_system,
                "focus_billing_period": str(r.row.get("BillingPeriodStart") or ""),
            }

    def to_untagged_rows(self, rows: list[FocusRowAdapter]) -> Iterator[dict[str, Any]]:
        for r in rows:
            yield {
                "id": f"unt-{uuid.uuid4().hex[:16]}",
                "detected_at": datetime.now(UTC).replace(tzinfo=None),
                "service_name": r.service_name,
                "resource_id": str(r.row.get("ResourceId") or ""),
                "resource_name": str(r.row.get("ResourceName") or ""),
                "cost_usd": r.effective_cost,
                "missing_tags": ",".join(
                    k for k in REQUIRED_TAGS if not r.tags.get(k)
                ),
                "billing_period": str(r.row.get("BillingPeriodStart") or ""),
            }
