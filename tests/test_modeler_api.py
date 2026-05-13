"""Integration: requirement → seed → refine → promote via FastAPI client."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_finops.api.routes import router
from ai_finops.db import Repository, get_session_factory, init_db
from ai_finops.modeler import DecisionEngine, TechnologySeeder
from ai_finops.services.cost_calculator import CostCalculator
from ai_finops.services.rate_card_service import RateCardService

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path) -> TestClient:
    db_url = f"sqlite:///{tmp_path}/i.sqlite"
    init_db(db_url)
    repo = Repository(get_session_factory(db_url))
    rates = RateCardService(rate_card_dir=REPO_ROOT / "config" / "rate_cards")
    rates.load()
    calc = CostCalculator(rates)
    seeder = TechnologySeeder(matrix_path=REPO_ROOT / "config" / "modeler" / "decision_matrix.yaml")
    engine = DecisionEngine(
        cost_calculator=calc,
        seeder=seeder,
        weights_path=REPO_ROOT / "config" / "modeler" / "decision_weights.yaml",
    )
    app = FastAPI()
    app.state.repository = repo
    app.state.rate_card_service = rates
    app.state.cost_calculator = calc
    app.state.technology_seeder = seeder
    app.state.decision_engine = engine
    # Wire the bare minimum services the existing routes pull from app.state.
    from ai_finops.modeler.scenario_comparison import ScenarioComparison
    from ai_finops.optimisation.recommender import OptimisationRecommender

    app.state.scenario_comparison = ScenarioComparison(calc)
    app.state.optimisation_recommender = OptimisationRecommender(rates)
    app.include_router(router)
    return TestClient(app)


def test_modeler_full_round_trip(client: TestClient) -> None:
    # 1. Capture requirement
    r = client.post(
        "/api/v1/modeler/requirements",
        json={
            "description": (
                "Tier-1 helpdesk for 4000 employees, must cite SharePoint "
                "policies, no external chat. Confidential data."
            )
        },
    )
    assert r.status_code == 200, r.text
    req_id = r.json()["id"]
    assert r.json()["parsed"]["audience"] == "employees"
    assert "sharepoint" in r.json()["parsed"]["must_ground_on"]

    # 2. Seed
    r = client.post("/api/v1/modeler/seed", json={"requirement_id": req_id})
    assert r.status_code == 200, r.text
    seed = r.json()
    session_id = seed["session_id"]
    assert seed["rationale_id"]
    assert seed["score"]["fit"] >= 0
    assert seed["alternatives"]
    # rationale chips include text and source citation
    assert seed["rationale"]["source"]

    # 3. Refine — change channel
    r = client.post(
        "/api/v1/modeler/refine",
        json={"session_id": session_id, "edits": {"channel": "web_chat"}},
    )
    assert r.status_code == 200, r.text
    refined = r.json()
    assert refined["profile"]["channel"] == "web_chat"

    # 4. Promote
    r = client.post(
        "/api/v1/modeler/promote",
        json={
            "session_id": session_id,
            "agent_name": "Tier-1 Helpdesk",
            "owner": "alice@contoso.com",
            "cost_center": "IT-12",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "promoted"
    agent_id = r.json()["agent_id"]

    # 5. Verify the AgentRow exists and ingestion-run audit captured it

    repo: Repository = client.app.state.repository
    runs = repo.list_ingestion_runs()
    jobs = {r["job"] for r in runs}
    assert "modeler_promote" in jobs

    agents = repo.list_agents()
    assert any(a["agent_id"] == agent_id for a in agents)


def test_data_sources_endpoint_lists_pullers(client: TestClient) -> None:
    r = client.get("/api/v1/data-sources")
    assert r.status_code == 200
    body = r.json()
    jobs = {s["job"] for s in body["sources"]}
    assert {"agent365", "purview", "defender", "azure_inventory", "cost_management"}.issubset(jobs)


def test_ingestion_run_returns_plan_when_no_factory(client: TestClient) -> None:
    r = client.post("/api/v1/ingestion/run", json={"jobs": ["agent365"]})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "plan"
    assert body["would_run"]
