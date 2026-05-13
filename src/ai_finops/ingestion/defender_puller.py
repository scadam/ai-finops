"""Microsoft Defender / XDR puller — security alerts + secure score per agent.

The canonical SDKs are ``azure-mgmt-security`` and ``msgraph-sdk-python``;
we use REST through Microsoft Graph Security to keep the dependency surface
small. Two outputs:

* ``AgentRiskSignalRow`` — one row per ``(agent_id, alert_id)`` pair, used
  by the Governance tab and as the ``risk`` input to the decision engine.
* Tenant secure-score snapshot — emitted as a single row keyed by date.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from ._http import TokenProvider, request_with_retry
from .scopes import GRAPH_BETA, GRAPH_SCOPE

logger = logging.getLogger(__name__)

SOURCE = "defender_xdr_graph"

_SEVERITY_MAP = {
    "informational": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "high",
}


class DefenderPuller:
    """Pull security alerts + secure-score from Microsoft Graph Security."""

    source_system = SOURCE
    sdk_call = (
        "GET /beta/security/alerts_v2, "
        "GET /beta/security/secureScores"
    )

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
            response = request_with_retry(
                self._client,
                "GET",
                f"{GRAPH_BETA}/security/secureScores?$top=1",
                headers=self._tokens.auth_header(GRAPH_SCOPE),
            )
            return response.status_code < 500
        except Exception as exc:
            logger.debug("Defender probe failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    def fetch_alerts(self, since: datetime | None = None) -> list[dict[str, Any]]:
        url = f"{GRAPH_BETA}/security/alerts_v2"
        if since is not None:
            ts = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            url += f"?$filter=createdDateTime ge {ts}"
        return self._page(url)

    def fetch_secure_scores(self, top: int = 1) -> list[dict[str, Any]]:
        return self._page(f"{GRAPH_BETA}/security/secureScores?$top={top}")

    # ------------------------------------------------------------------
    def _page(self, url: str) -> list[dict[str, Any]]:
        if self._client is None or self._tokens is None:
            raise RuntimeError("DefenderPuller requires HTTP client + TokenProvider.")
        rows: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            response = request_with_retry(
                self._client, "GET", next_url, headers=self._tokens.auth_header(GRAPH_SCOPE)
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Defender call failed: {response.status_code} {response.text[:200]}"
                )
            data = response.json()
            rows.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
        return rows

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_id_from_alert(alert: dict[str, Any]) -> str:
        """Extract the affected agent / service-principal id from an alert."""
        # Graph alerts_v2 puts service-principal evidence in evidence[].appId.
        for ev in alert.get("evidence") or []:
            if isinstance(ev, dict):
                app_id = ev.get("appId") or ev.get("servicePrincipalId")
                if app_id:
                    return str(app_id)
        # Fallback: legacy actorDisplayName.
        actor = alert.get("actorDisplayName") or ""
        return str(actor) if actor else ""

    def normalise_alerts(self, alerts: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Emit ``AgentRiskSignalRow``-shaped dicts."""
        for a in alerts:
            alert_id = str(a.get("id") or "")
            if not alert_id:
                continue
            agent_id = self._agent_id_from_alert(a)
            severity_raw = str(a.get("severity") or "").lower()
            severity = _SEVERITY_MAP.get(severity_raw, "medium")
            yield {
                "id": f"def-{alert_id[:32]}",
                "captured_at": datetime.now(UTC).replace(tzinfo=None),
                "agent_id": agent_id,
                "alert_id": alert_id,
                "title": str(a.get("title") or "")[:256],
                "severity": severity,
                "status": str(a.get("status") or "newAlert"),
                "category": str(a.get("category") or ""),
                "service_source": str(a.get("serviceSource") or ""),
                "description": str(a.get("description") or "")[:1024],
                "source_system": SOURCE,
                "raw_record_id": alert_id,
            }

    def normalise_secure_score(self, scores: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for s in scores:
            score_id = str(s.get("id") or s.get("createdDateTime") or "")
            yield {
                "id": f"sec-{score_id[:32]}" if score_id else None,
                "captured_at": datetime.now(UTC).replace(tzinfo=None),
                "agent_id": "",  # tenant-wide
                "alert_id": "",
                "title": "Secure score",
                "severity": "low",
                "status": "informational",
                "category": "secure_score",
                "service_source": "defender",
                "description": (
                    f"current={s.get('currentScore')} max={s.get('maxScore')} "
                    f"as_of={s.get('createdDateTime')}"
                )[:1024],
                "source_system": SOURCE,
                "raw_record_id": score_id,
            }
