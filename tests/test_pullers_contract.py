"""Contract tests for SDK pullers — fed from recorded JSON fixtures.

No live network calls. Each test instantiates the puller with a stub HTTP
client that replays a canned response, then asserts the puller emits the
contract documented in ``problem_statement`` Part 1 §2.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from ai_finops.ingestion import (
    Agent365DirectoryPuller,
    Agent365UsagePuller,
    AzureInventoryPuller,
    DefenderPuller,
    EntraDirectoryPuller,
    PowerPlatformPuller,
    PurviewPuller,
)
from ai_finops.ingestion._http import TokenProvider


class StubToken(TokenProvider):
    def __init__(self) -> None:
        # Avoid building a real DefaultAzureCredential.
        pass

    def get_token(self, scope: str) -> str:  # type: ignore[override]
        return "stub-token"

    def auth_header(self, scope: str) -> dict[str, str]:  # type: ignore[override]
        return {"Authorization": "Bearer stub-token"}


def _client_returning(payloads: dict[str, Any]) -> httpx.Client:
    """Build an httpx.Client that returns canned JSON per matching URL prefix."""

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, body in payloads.items():
            if prefix in str(request.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------
def test_agent365_directory_normalises_agents_and_owners() -> None:
    payloads = {
        "/owners": {  # matched first to avoid /beta/agents prefix capture
            "value": [{"id": "u-1", "userPrincipalName": "alice@contoso.com",
                       "displayName": "Alice"}]
        },
        "/beta/agents": {
            "value": [
                {
                    "id": "ag-1",
                    "displayName": "Helpdesk",
                    "agentType": "declarative_tenant",
                    "publisher": "Contoso",
                    "channel": "m365_copilot",
                    "ownerIds": ["u-1"],
                }
            ]
        },
    }
    client = _client_returning(payloads)
    puller = Agent365DirectoryPuller(token_provider=StubToken(), client=client)
    raw = puller.fetch()
    assert len(raw) == 1
    agents = list(puller.normalise_agents(raw))
    assert agents[0]["agent_id"] == "ag-1"
    assert agents[0]["agent_365_registered"] is True
    owners = list(puller.normalise_owners("ag-1", puller.fetch_owners("ag-1")))
    assert owners[0]["owner_upn"] == "alice@contoso.com"
    assert owners[0]["agent_id"] == "ag-1"
    assert owners[0]["source_system"] == "agent365_directory_api"


def test_agent365_usage_uses_beta_endpoint() -> None:
    """The usage puller must hit /beta/reports/getAgent365UsageReport."""
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "rpt-1",
                        "agentId": "ag-1",
                        "agentName": "Helpdesk",
                        "channel": "m365_copilot",
                        "creditsUsed": 250,
                        "shadowCredits": 0,
                        "isZeroRated": False,
                        "reportDate": "2025-01-01T00:00:00Z",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    puller = Agent365UsagePuller(token_provider=StubToken(), client=client)
    raw = puller.fetch()
    assert any("/beta/reports/getAgent365UsageReport" in u for u in captured)
    events = list(puller.normalise(raw))
    assert events
    for ev in events:
        assert ev["source_system"] == "agent365_usage_report"
        assert ev["meter"]


def test_entra_directory_normalises_population() -> None:
    payloads = {
        "/beta/subscribedSkus": {
            "value": [
                {
                    "skuId": "sku-1",
                    "skuPartNumber": "M365_COPILOT",
                    "consumedUnits": 80,
                    "prepaidUnits": {"enabled": 100},
                }
            ]
        },
        "/beta/users": {
            "value": [
                {"id": "u-1", "userPrincipalName": "a@x", "assignedLicenses": [{"skuId": "sku-1"}],
                 "signInActivity": {"lastSignInDateTime": "2099-01-01T00:00:00Z"}},
                {"id": "u-2", "userPrincipalName": "b@x", "assignedLicenses": [{"skuId": "sku-1"}],
                 "signInActivity": {"lastSignInDateTime": "1999-01-01T00:00:00Z"}},
            ]
        },
    }
    client = _client_returning(payloads)
    puller = EntraDirectoryPuller(token_provider=StubToken(), client=client)
    skus = puller.fetch_subscribed_skus()
    users = puller.fetch_users_with_signin()
    rows = list(puller.normalise_licensed_population(skus, users))
    assert len(rows) == 1
    assert rows[0]["assigned_users"] == 2
    assert rows[0]["active_users_30d"] == 1
    assert rows[0]["source_system"] == "entra_licensing_api"


def test_purview_normalises_labels() -> None:
    labels = [
        {"id": "lab-1", "displayName": "Confidential", "sensitivity": "confidential",
         "tooltip": "internal use"},
    ]
    dlp = [{"id": "dlp-1", "appliedLabels": ["lab-1"]}]
    classes = [{"name": "PII", "labelId": "lab-1"}]
    puller = PurviewPuller(token_provider=StubToken(), client=_client_returning({}))
    rows = list(puller.normalise_labels(labels, dlp, classes))
    assert rows[0]["label_id"] == "lab-1"
    assert rows[0]["dlp_policy_count"] == 1
    assert rows[0]["classification_count"] == 1
    assert rows[0]["source_system"] == "purview_compliance_graph"


def test_defender_normalises_alerts_and_secure_score() -> None:
    alerts = [
        {"id": "alt-1", "title": "Risky sign-in", "severity": "high",
         "status": "newAlert", "category": "InitialAccess",
         "serviceSource": "microsoftAadIdentityProtection",
         "evidence": [{"@odata.type": "#microsoft.graph.security.servicePrincipalEvidence",
                       "appId": "app-1"}],
         "description": "Bad"}
    ]
    puller = DefenderPuller(token_provider=StubToken(), client=_client_returning({}))
    rows = list(puller.normalise_alerts(alerts))
    assert rows[0]["alert_id"] == "alt-1"
    assert rows[0]["agent_id"] == "app-1"
    assert rows[0]["source_system"] == "defender_xdr_graph"
    scores = [{"id": "s-1", "currentScore": 600.0, "maxScore": 800.0,
               "createdDateTime": "2025-01-01T00:00:00Z"}]
    rows = list(puller.normalise_secure_score(scores))
    assert "secure score" in rows[0]["title"].lower()


def test_power_platform_normalises_environments() -> None:
    envs = [
        {
            "name": "env-1",
            "properties": {
                "displayName": "Default Env",
                "location": "unitedstates",
                "environmentSku": "Default",
                "isDefault": True,
                "capacity": {"creditPoolTotal": 1000, "creditPoolConsumed": 200},
            },
        }
    ]
    dlp = [{"properties": {"environments": [{"name": "env-1"}]}}]
    puller = PowerPlatformPuller(token_provider=StubToken(), client=_client_returning({}))
    rows = list(puller.normalise_environments(envs, dlp))
    assert rows[0]["environment_id"] == "env-1"
    assert rows[0]["dlp_policy_count"] == 1
    assert rows[0]["source_system"] == "power_platform_admin_api"


def test_azure_inventory_normalises_resources() -> None:
    resources = [
        {
            "id": "/subscriptions/s/providers/Microsoft.Search/searchServices/x",
            "name": "search1",
            "type": "Microsoft.Search/searchServices",
            "location": "eastus",
            "sku": {"name": "standard"},
            "tags": {"AgentId": "agt-1"},
        }
    ]
    puller = AzureInventoryPuller(
        token_provider=StubToken(),
        client=_client_returning({}),
        subscription_id="s",
    )
    rows = list(puller.normalise(resources))
    assert rows[0]["kind"] == "ai_search"
    assert rows[0]["sku_name"] == "standard"
    assert rows[0]["source_system"] == "azure_resource_manager"


# ---------------------------------------------------------------------
def test_repository_rejects_unattributed_cost_event(tmp_path) -> None:
    """Source-system enforcement — Part 1 §4 of the plan."""
    from datetime import datetime
    from decimal import Decimal

    from ai_finops.db import Repository, get_session_factory, init_db

    db_url = f"sqlite:///{tmp_path}/x.sqlite"
    init_db(db_url)
    repo = Repository(get_session_factory(db_url))
    with pytest.raises(ValueError, match="source_system"):
        repo.insert_cost_events([
            {
                "timestamp": datetime.utcnow(),
                "meter": "azure_consumption",
                "agent_id": "agt-1",
                "cost_actual_usd": Decimal("1"),
            }
        ])
