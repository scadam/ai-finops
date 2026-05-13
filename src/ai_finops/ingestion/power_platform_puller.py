"""Power Platform admin puller — environments, DLP, capacity, Studio bots.

Uses the Power Platform admin REST surfaces (no Python SDK is GA at the time
of writing — ``Microsoft.PowerPlatform.Cds.Client`` is .NET-only). All calls
go through ``api.bap.microsoft.com`` and ``api.powerplatform.com``.

Outputs:

* ``PowerPlatformEnvironmentRow`` — one row per environment with credit
  pool size, region, sku, dlp connector group counts.
* ``CostEventRow`` rows on the credits meter for any environment-level
  capacity add-on consumption.
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
from .scopes import POWER_PLATFORM_BAP, POWER_PLATFORM_PPAI, POWER_PLATFORM_SCOPE

logger = logging.getLogger(__name__)

SOURCE = "power_platform_admin_api"


class PowerPlatformPuller:
    """Read environment, DLP, and capacity inventory from Power Platform."""

    source_system = SOURCE
    sdk_call = (
        "GET https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/scopes/admin/environments, "
        "GET https://api.bap.microsoft.com/providers/PowerPlatform.Governance/v2/policies, "
        "GET https://api.powerplatform.com/licensing/environments/{env}/allocations"
    )

    API_VERSION_BAP = "2022-03-01-preview"
    API_VERSION_PPAI = "2023-09-30-preview"

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._tokens = token_provider
        self._client = client

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None:
            return False
        try:
            url = (
                f"{POWER_PLATFORM_BAP}/providers/Microsoft.BusinessAppPlatform/"
                f"scopes/admin/environments?api-version={self.API_VERSION_BAP}&$top=1"
            )
            response = request_with_retry(
                self._client, "GET", url,
                headers=self._tokens.auth_header(POWER_PLATFORM_SCOPE),
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Power Platform probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    def fetch_environments(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("PowerPlatformPuller requires HTTP client + TokenProvider.")
        url = (
            f"{POWER_PLATFORM_BAP}/providers/Microsoft.BusinessAppPlatform/"
            f"scopes/admin/environments?api-version={self.API_VERSION_BAP}"
        )
        response = request_with_retry(
            self._client, "GET", url,
            headers=self._tokens.auth_header(POWER_PLATFORM_SCOPE),
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Power Platform environments failed: {response.status_code} {response.text[:200]}"
            )
        return list(response.json().get("value", []))

    def fetch_dlp_policies(self) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            return []
        try:
            url = (
                f"{POWER_PLATFORM_BAP}/providers/PowerPlatform.Governance/"
                f"v2/policies?api-version={self.API_VERSION_BAP}"
            )
            response = request_with_retry(
                self._client, "GET", url,
                headers=self._tokens.auth_header(POWER_PLATFORM_SCOPE),
            )
            if response.status_code >= 400:
                return []
            return list(response.json().get("value", []))
        except Exception as exc:
            logger.warning("Power Platform DLP fetch failed: %s", exc)
            return []

    def fetch_capacity(self, environment_id: str) -> dict[str, Any]:
        if self._client is None or self._tokens is None:
            return {}
        try:
            url = (
                f"{POWER_PLATFORM_PPAI}/licensing/environments/{environment_id}/"
                f"allocations?api-version={self.API_VERSION_PPAI}"
            )
            response = request_with_retry(
                self._client, "GET", url,
                headers=self._tokens.auth_header(POWER_PLATFORM_SCOPE),
            )
            if response.status_code >= 400:
                return {}
            return response.json()
        except Exception as exc:
            logger.warning("Power Platform capacity fetch failed for %s: %s", environment_id, exc)
            return {}

    # ------------------------------------------------------------------
    def normalise_environments(
        self,
        environments: list[dict[str, Any]],
        dlp_policies: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        dlp_policies = dlp_policies or []
        ts = datetime.now(UTC).replace(tzinfo=None)
        for env in environments:
            env_id = str(env.get("name") or env.get("id") or "")
            if not env_id:
                continue
            props = env.get("properties") or {}
            display_name = str(props.get("displayName") or env_id)
            region = str(props.get("location") or "")
            sku = str(props.get("environmentSku") or "")
            applied_policies = sum(
                1 for p in dlp_policies
                if env_id in {
                    str(e.get("name") or "")
                    for e in (p.get("properties", {}) or {}).get("environments", [])
                }
            )
            yield {
                "environment_id": env_id,
                "captured_at": ts,
                "display_name": display_name,
                "region": region,
                "sku": sku,
                "is_default": bool(props.get("isDefault")),
                "credit_pool_total": int((props.get("capacity") or {}).get("creditPoolTotal") or 0),
                "credit_pool_consumed": int((props.get("capacity") or {}).get("creditPoolConsumed") or 0),
                "dlp_policy_count": applied_policies,
                "source_system": SOURCE,
                "raw_record_id": env_id,
            }

    def normalise_capacity_events(
        self,
        environment_id: str,
        capacity: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """Emit credit-meter ``CostEventRow`` dicts for environment capacity."""
        consumed = int(capacity.get("creditsConsumed") or 0)
        if not consumed:
            return
        payg_rate = Decimal("0.01")
        yield {
            "id": f"pp-{uuid.uuid4().hex[:16]}",
            "timestamp": datetime.now(UTC),
            "meter": Meter.COPILOT_CREDITS.value,
            "agent_id": environment_id,
            "agent_name": str(capacity.get("environmentName") or environment_id),
            "agent_type": AgentType.COPILOT_STUDIO_CUSTOM.value,
            "channel": Channel.CUSTOM_CHANNEL.value,
            "user_license_type": UserLicenseType.INTERNAL_UNLICENSED.value,
            "credits_consumed": consumed,
            "credits_shadow": 0,
            "b2e_zero_rated": False,
            "cost_actual_usd": Decimal(consumed) * payg_rate,
            "source_system": SOURCE,
            "raw_record_id": str(capacity.get("id") or environment_id),
        }
