"""Agent 365 directory + usage pullers (Microsoft Graph beta).

The canonical SDK is ``msgraph-beta-sdk-python`` but at the time of writing
the ``/agents`` resource is only exposed via the beta REST endpoint, so we
call it directly through :class:`~ai_finops.ingestion._http.TokenProvider`.

Two pullers live in this module:

* :class:`Agent365DirectoryPuller` — emits ``AgentRow``-shaped dicts keyed on
  ``agent_id`` (the Entra Agent ID). Replaces hand-tagging.
* :class:`Agent365UsagePuller`     — emits ``CostEventRow``-shaped dicts on
  the ``COPILOT_CREDITS`` meter using ``getAgent365UsageReport``.
"""
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
from .scopes import GRAPH_BETA, GRAPH_SCOPE

logger = logging.getLogger(__name__)

SOURCE_DIRECTORY = "agent365_directory_api"
SOURCE_USAGE = "agent365_usage_report"


# ---------------------------------------------------------------------------
# Agent type / channel mapping helpers
# ---------------------------------------------------------------------------
_AGENT_TYPE_MAP = {
    "declarative": AgentType.DECLARATIVE_INSTRUCTION,
    "declarative_instruction": AgentType.DECLARATIVE_INSTRUCTION,
    "declarative_tenant": AgentType.DECLARATIVE_TENANT,
    "declarative_public": AgentType.DECLARATIVE_PUBLIC,
    "copilot_studio_custom": AgentType.COPILOT_STUDIO_CUSTOM,
    "studio": AgentType.COPILOT_STUDIO_CUSTOM,
    "foundry_native": AgentType.FOUNDRY_NATIVE,
    "foundry": AgentType.FOUNDRY_NATIVE,
    "foundry_hosted": AgentType.FOUNDRY_HOSTED,
    "hybrid": AgentType.HYBRID_STUDIO_FOUNDRY,
    "hybrid_studio_foundry": AgentType.HYBRID_STUDIO_FOUNDRY,
}


def _coerce_agent_type(value: Any) -> AgentType:
    if not value:
        return AgentType.COPILOT_STUDIO_CUSTOM
    return _AGENT_TYPE_MAP.get(str(value).lower(), AgentType.COPILOT_STUDIO_CUSTOM)


def _coerce_channel(value: Any) -> Channel:
    text = str(value or "").lower()
    if "teams" in text:
        return Channel.TEAMS_COPILOT_EXTENSION
    if "web" in text:
        return Channel.WEB_CHAT
    if "custom" in text:
        return Channel.CUSTOM_CHANNEL
    return Channel.M365_COPILOT


def _parse_ts(raw: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Directory puller
# ---------------------------------------------------------------------------
class Agent365DirectoryPuller:
    """Self-discover every Agent 365-registered agent in the tenant."""

    source_system = SOURCE_DIRECTORY
    sdk_call = "GET /beta/agents (Microsoft Graph)"

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._tokens = token_provider
        self._client = client

    # --------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None:
            return False
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/agents?$top=1",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            return response.status_code < 400
        except Exception as exc:
            logger.debug("Agent365 directory probe failed: %s", exc)
            return False

    # --------------------------------------------------------------
    def fetch(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("Agent365DirectoryPuller requires HTTP client + TokenProvider.")
        url: str | None = f"{GRAPH_BETA}/agents"
        rows: list[dict[str, Any]] = []
        while url:
            response = request_with_retry(
                self._client, "GET", url, headers=self._tokens.auth_header(GRAPH_SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Agent365 directory failed: {response.status_code} {response.text[:200]}"
                )
            payload = response.json()
            rows.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
        return rows

    # --------------------------------------------------------------
    def fetch_owners(self, agent_id: str) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            return []
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/agents/{agent_id}/owners",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            if response.status_code >= 400:
                return []
            return list(response.json().get("value", []))
        except Exception as exc:
            logger.debug("Owner fetch failed for %s: %s", agent_id, exc)
            return []

    # --------------------------------------------------------------
    def normalise_agents(self, rows: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield ``AgentRow``-shaped dicts."""
        for row in rows:
            agent_id = str(row.get("id") or row.get("agentId") or "")
            if not agent_id:
                continue
            owner_upn = ""
            owners = row.get("owners") or []
            if owners and isinstance(owners[0], dict):
                owner_upn = str(owners[0].get("userPrincipalName") or owners[0].get("upn") or "")
            data_sources = row.get("dataSources") or []
            uses_tenant_graph = any(
                "graph" in str(d.get("kind", "")).lower() or "sharepoint" in str(d.get("kind", "")).lower()
                for d in data_sources
            )
            uses_dataverse = any("dataverse" in str(d.get("kind", "")).lower() for d in data_sources)
            uses_public_web = any("web" in str(d.get("kind", "")).lower() for d in data_sources)
            yield {
                "agent_id": agent_id,
                "agent_name": str(row.get("displayName") or agent_id),
                "agent_type": _coerce_agent_type(row.get("agentType")).value,
                "channel": _coerce_channel(row.get("channel")).value,
                "build_platform": str(row.get("publisher") or "agent_365"),
                "owner": owner_upn,
                "environment": str(row.get("environment") or "prod"),
                "status": str(row.get("status") or "production"),
                "uses_tenant_graph": uses_tenant_graph,
                "uses_public_web": uses_public_web,
                "uses_dataverse": uses_dataverse,
                "agent_365_registered": True,
                "agent_365_owner_upn": owner_upn or None,
            }

    def normalise_owners(self, agent_id: str, owners: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield ``AgentOwnerRow``-shaped dicts."""
        for o in owners:
            upn = str(o.get("userPrincipalName") or o.get("upn") or "")
            object_id = str(o.get("id") or "")
            if not upn and not object_id:
                continue
            yield {
                "agent_id": agent_id,
                "owner_upn": upn,
                "owner_object_id": object_id,
                "owner_display_name": str(o.get("displayName") or upn or object_id),
                "source_system": SOURCE_DIRECTORY,
                "raw_record_id": object_id or upn,
            }


# ---------------------------------------------------------------------------
# Usage puller
# ---------------------------------------------------------------------------
class Agent365UsagePuller:
    """Per-agent usage report → ``CostEventRow`` dicts (credits meter)."""

    source_system = SOURCE_USAGE
    sdk_call = "GET /beta/reports/getAgent365UsageReport (Microsoft Graph)"

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        period: str = "D30",
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._period = period

    # --------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None:
            return False
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/reports/getAgent365UsageReport(period='D7')",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Agent365 usage probe failed: %s", exc)
            return False

    # --------------------------------------------------------------
    def fetch(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("Agent365UsagePuller requires HTTP client + TokenProvider.")
        url: str | None = (
            f"{GRAPH_BETA}/reports/getAgent365UsageReport(period='{self._period}')"
        )
        rows: list[dict[str, Any]] = []
        while url:
            response = request_with_retry(
                self._client, "GET", url, headers=self._tokens.auth_header(GRAPH_SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Agent365 usage report failed: {response.status_code} {response.text[:200]}"
                )
            payload = response.json()
            rows.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
        return rows

    # --------------------------------------------------------------
    def normalise(self, rows: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        payg_rate = Decimal("0.01")
        for row in rows:
            credits_used = int(row.get("creditsUsed") or row.get("credits") or 0)
            shadow = int(row.get("shadowCredits") or 0)
            zero_rated = bool(row.get("isZeroRated"))
            consumed = 0 if zero_rated else credits_used
            agent_id = str(row.get("agentId") or "")
            raw_id = str(row.get("id") or row.get("recordId") or f"{agent_id}-{row.get('reportDate')}")
            yield {
                "id": f"a365-{uuid.uuid4().hex[:16]}",
                "timestamp": _parse_ts(row.get("reportDate")),
                "meter": Meter.COPILOT_CREDITS.value,
                "agent_id": agent_id,
                "agent_name": str(row.get("agentName") or agent_id),
                "agent_type": AgentType.COPILOT_STUDIO_CUSTOM.value,
                "channel": _coerce_channel(row.get("channel")).value,
                "user_license_type": (
                    UserLicenseType.M365_COPILOT_LICENSED.value
                    if zero_rated
                    else UserLicenseType.INTERNAL_UNLICENSED.value
                ),
                "credits_consumed": consumed,
                "credits_shadow": shadow if zero_rated else 0,
                "b2e_zero_rated": zero_rated,
                "cost_actual_usd": Decimal(consumed) * payg_rate,
                "source_system": SOURCE_USAGE,
                "raw_record_id": raw_id,
            }
