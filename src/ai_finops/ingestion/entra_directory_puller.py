"""Entra ID directory puller (users, groups, service principals, sign-ins).

Provides three normalised outputs:

* ``LicensedPopulationRow`` — count of users assigned each Copilot SKU and
  count of those active in the last 30 days (drives ``LICENSE_RIGHT_SIZING``
  recommendations with real evidence).
* ``AgentOwnerRow``         — owner UPN/objectId for every Entra application
  whose displayName matches the Agent 365 catalogue (used to enrich agents
  not yet in the Agent 365 directory).
* ``AgentRow`` enrichment   — owner + cost-center via app extension attrs.

The canonical SDK is ``msgraph-sdk-python``; we use REST to keep our wheel
small and to share the existing TokenProvider retry logic.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ._http import TokenProvider, request_with_retry
from .scopes import GRAPH_BETA, GRAPH_SCOPE

logger = logging.getLogger(__name__)

SOURCE_DIRECTORY = "entra_directory_api"
SOURCE_LICENSING = "entra_licensing_api"
SOURCE_SIGN_INS = "entra_signin_activity"


class EntraDirectoryPuller:
    """Pull users / groups / service principals + signInActivity."""

    source_system = SOURCE_DIRECTORY
    sdk_call = (
        "GET /beta/users?$select=assignedLicenses,signInActivity, "
        "GET /beta/subscribedSkus, GET /beta/servicePrincipals"
    )

    # Subset of M365 Copilot SKU part numbers we care about — checked
    # case-insensitively against the user's assignedLicenses.
    COPILOT_SKU_TOKENS = (
        "copilot",
        "m365_copilot",
        "microsoft_365_copilot",
        "m365_e7",
    )

    def __init__(
        self,
        token_provider: TokenProvider | None = None,
        client: httpx.Client | None = None,
        active_window_days: int = 30,
    ) -> None:
        self._tokens = token_provider
        self._client = client
        self._active_window = timedelta(days=active_window_days)

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        if self._client is None or self._tokens is None:
            return False
        try:
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/subscribedSkus?$top=1",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            return response.status_code < 400
        except Exception as exc:
            logger.debug("Entra probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    def fetch_subscribed_skus(self) -> list[dict[str, Any]]:
        return self._page(f"{GRAPH_BETA}/subscribedSkus")

    def fetch_users_with_signin(self, page_size: int = 200) -> list[dict[str, Any]]:
        url = (
            f"{GRAPH_BETA}/users?$select=id,userPrincipalName,assignedLicenses,signInActivity"
            f"&$top={page_size}"
        )
        return self._page(url)

    def fetch_service_principals(self, name_filter: str | None = None) -> list[dict[str, Any]]:
        url = f"{GRAPH_BETA}/servicePrincipals?$top=200"
        if name_filter:
            # Defensive escaping (single quotes are the OData escape char).
            safe = name_filter.replace("'", "''")
            url += f"&$filter=startswith(displayName,'{safe}')"
        return self._page(url)

    # ------------------------------------------------------------------
    def _page(self, url: str) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("EntraDirectoryPuller requires HTTP client + TokenProvider.")
        rows: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            response = request_with_retry(
                self._client, "GET", next_url, headers=self._tokens.auth_header(GRAPH_SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Entra Graph call failed: {response.status_code} {response.text[:200]}"
                )
            data = response.json()
            rows.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
        return rows

    # ------------------------------------------------------------------
    def normalise_licensed_population(
        self,
        skus: list[dict[str, Any]],
        users: list[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        """Emit one row per Copilot SKU with assigned + active counts."""
        sku_id_to_part: dict[str, str] = {}
        for sku in skus:
            sku_id = str(sku.get("skuId") or "")
            part = str(sku.get("skuPartNumber") or "").lower()
            if not sku_id or not part:
                continue
            if not any(t in part for t in self.COPILOT_SKU_TOKENS):
                continue
            sku_id_to_part[sku_id] = part

        cutoff = datetime.now(UTC) - self._active_window
        counts = {sku_id: {"assigned": 0, "active": 0} for sku_id in sku_id_to_part}
        for u in users:
            assigned = [str(lic.get("skuId") or "") for lic in (u.get("assignedLicenses") or [])]
            last_sign_in_raw = (u.get("signInActivity") or {}).get("lastSignInDateTime")
            try:
                last_sign_in = (
                    datetime.fromisoformat(str(last_sign_in_raw).replace("Z", "+00:00"))
                    if last_sign_in_raw
                    else None
                )
            except ValueError:
                last_sign_in = None
            for sku_id in assigned:
                if sku_id not in counts:
                    continue
                counts[sku_id]["assigned"] += 1
                if last_sign_in and last_sign_in >= cutoff:
                    counts[sku_id]["active"] += 1

        ts = datetime.now(UTC).replace(tzinfo=None)
        for sku_id, c in counts.items():
            yield {
                "sku_id": sku_id,
                "sku_part_number": sku_id_to_part[sku_id],
                "captured_at": ts,
                "assigned_users": c["assigned"],
                "active_users_30d": c["active"],
                "active_pct": (
                    round(100.0 * c["active"] / c["assigned"], 2) if c["assigned"] else 0.0
                ),
                "source_system": SOURCE_LICENSING,
                "raw_record_id": sku_id,
            }

    # ------------------------------------------------------------------
    def normalise_owners(
        self, service_principals: list[dict[str, Any]]
    ) -> Iterator[dict[str, Any]]:
        """Emit AgentOwnerRow-shaped dicts from SP owner lookups."""
        for sp in service_principals:
            agent_id = str(sp.get("appId") or sp.get("id") or "")
            owners = sp.get("owners") or []
            for o in owners:
                upn = str(o.get("userPrincipalName") or o.get("upn") or "")
                obj_id = str(o.get("id") or "")
                if not upn and not obj_id:
                    continue
                yield {
                    "agent_id": agent_id,
                    "owner_upn": upn,
                    "owner_object_id": obj_id,
                    "owner_display_name": str(o.get("displayName") or upn or obj_id),
                    "source_system": SOURCE_DIRECTORY,
                    "raw_record_id": obj_id or upn,
                }
