"""Tests for the deterministic decision engine."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_finops.modeler import (
    AgentRequirement,
    DecisionEngine,
    TechnologySeeder,
)
from ai_finops.modeler.seeder import TenantFacts
from ai_finops.services.cost_calculator import CostCalculator
from ai_finops.services.rate_card_service import RateCardService

CFG = Path(__file__).resolve().parent.parent / "config" / "modeler"
RATES = Path(__file__).resolve().parent.parent / "config" / "rate_cards"


@pytest.fixture(scope="module")
def calc() -> CostCalculator:
    rcs = RateCardService(rate_card_dir=RATES)
    rcs.load()
    return CostCalculator(rcs)


@pytest.fixture(scope="module")
def seeder() -> TechnologySeeder:
    return TechnologySeeder(matrix_path=CFG / "decision_matrix.yaml")


@pytest.fixture
def engine(calc: CostCalculator, seeder: TechnologySeeder) -> DecisionEngine:
    return DecisionEngine(
        cost_calculator=calc,
        seeder=seeder,
        weights_path=CFG / "decision_weights.yaml",
    )


def _req() -> AgentRequirement:
    return AgentRequirement(
        audience="employees",
        audience_size=1000,
        data_sensitivity="confidential",
        must_ground_on=["sharepoint", "graph"],
        tools_required=["lookup"],
    )


def test_engine_is_deterministic(engine: DecisionEngine, seeder: TechnologySeeder) -> None:
    req = _req()
    seeded = seeder.seed(req)
    a = engine.score(seeded.profile, seeded.usage, req)
    b = engine.score(seeded.profile, seeded.usage, req)
    assert a == b
    assert a.total == b.total


def test_engine_logs_inputs_and_rationale(
    engine: DecisionEngine, seeder: TechnologySeeder
) -> None:
    req = _req()
    seeded = seeder.seed(req)
    score = engine.score(seeded.profile, seeded.usage, req, TenantFacts(risk_alert_count=2))
    # The contract: every dimension is reproducible from inputs alone.
    assert "weights" in score.inputs
    assert score.inputs["agent_type"] == seeded.profile.agent_type.value
    assert score.inputs["risk_alerts_high"] == 2
    assert any("fit=" in line for line in score.rationale)
    assert any("compliance=" in line for line in score.rationale)


def test_engine_compliance_gate_for_restricted(
    engine: DecisionEngine, seeder: TechnologySeeder
) -> None:
    """Restricted-data customer agent must be compliant; declarative_public must not."""
    req = AgentRequirement(audience="customers", data_sensitivity="restricted")
    seeded = seeder.seed(req)  # picks foundry_native (cell #1)
    assert seeded.profile.agent_type.value == "foundry_native"
    base = engine.score(seeded.profile, seeded.usage, req)
    assert base.compliance == 1.0

    from dataclasses import replace

    from ai_finops.domain.enums import AgentType

    bad_profile = replace(seeded.profile, agent_type=AgentType.DECLARATIVE_PUBLIC)
    bad = engine.score(bad_profile, seeded.usage, req)
    assert bad.compliance == 0.0
    assert bad.total < base.total


def test_engine_alternatives_ranked(
    engine: DecisionEngine, seeder: TechnologySeeder
) -> None:
    req = _req()
    seeded = seeder.seed(req)
    ranked = engine.alternatives(seeded, req)
    assert len(ranked) > 1
    totals = [c.score.total for c in ranked]
    assert totals == sorted(totals, reverse=True)
