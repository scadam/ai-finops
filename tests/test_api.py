"""Smoke tests for FastAPI routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ai_finops.main import create_app


def test_root_and_health():
    app = create_app()
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "ai-finops"

    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # All 6 rate cards loaded
    assert len(body["rate_cards"]) == 6


def test_rate_cards_endpoint():
    client = TestClient(create_app())
    r = client.get("/api/v1/rate-cards")
    assert r.status_code == 200
    body = r.json()
    for k in ("per_seat", "copilot_credits", "azure_openai", "foundry_agent_service", "ai_search", "azure_infrastructure"):
        assert k in body and body[k]


def test_estimate_endpoint_b2e_zero_rated():
    client = TestClient(create_app())
    payload = {
        "profile": {
            "agent_id": "demo-agent",
            "agent_name": "Demo Agent",
            "agent_type": "copilot_studio_custom",
            "channel": "m365_copilot",
            "licensed_user_count": 100,
            "avg_interactions_per_user_per_month": 50,
        },
        "usage": {"generative_answers_per_interaction": 1},
        "period_months": 1,
    }
    r = client.post("/api/v1/agents/demo-agent/estimate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["b2e_zero_rated"] is True
    assert float(body["credits_cost_payg_usd"]) == 0.0


def test_compare_endpoint_returns_cheapest():
    client = TestClient(create_app())
    payload = {
        "base_profile": {
            "agent_name": "Compare-X",
            "channel": "m365_copilot",
            "unlicensed_user_count": 100,
            "avg_interactions_per_user_per_month": 50,
            "primary_model_id": "gpt_4o_mini",
            "avg_tokens_input_per_interaction": 500,
            "avg_tokens_output_per_interaction": 200,
        },
        "usage": {"generative_answers_per_interaction": 1},
        "period_months": 1,
    }
    r = client.post("/api/v1/scenarios/compare", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cheapest"] is not None
    assert len(body["results"]) >= 5
    # Sorted ascending by total monthly
    totals = [float(b["total_monthly_usd"]) for b in body["results"]]
    assert totals == sorted(totals)
