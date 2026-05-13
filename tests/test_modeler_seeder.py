"""Tests for the deterministic requirement parser + technology seeder."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_finops.modeler import (
    AgentRequirement,
    RequirementParser,
    TechnologySeeder,
    parse_free_text,
)
from ai_finops.modeler.seeder import TenantFacts

MATRIX = Path(__file__).resolve().parent.parent / "config" / "modeler" / "decision_matrix.yaml"


# ---------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------
def test_parser_extracts_known_axes() -> None:
    req = parse_free_text(
        "Tier-1 helpdesk for 4000 employees, must cite SharePoint policies, "
        "no external chat. Confidential data. Respond in 800 ms. "
        "30 interactions per user/month. GDPR applies."
    )
    assert req.audience == "employees"
    assert req.audience_size == 4000
    assert req.data_sensitivity == "confidential"
    assert "sharepoint" in req.must_ground_on
    assert req.expected_interactions_per_user_per_month == 30
    assert req.latency_target_ms == 800
    assert "gdpr" in req.compliance_constraints


def test_parser_is_deterministic() -> None:
    text = "Customer-facing chat agent backed by custom API, public web grounding"
    a = parse_free_text(text)
    b = parse_free_text(text)
    # ids will differ; everything else must match.
    a.id = b.id = "x"
    assert a == b
    assert a.audience == "customers"
    assert "custom_api" in a.must_ground_on
    assert "web" in a.must_ground_on


def test_parser_recognises_workflow_trigger() -> None:
    req = RequirementParser().parse("Approval workflow trigger flow on submit")
    assert "workflow_trigger" in req.tools_required


# ---------------------------------------------------------------------
# Seeder snapshot — every cell of the matrix
# ---------------------------------------------------------------------
@pytest.fixture
def seeder() -> TechnologySeeder:
    return TechnologySeeder(matrix_path=MATRIX)


def test_seed_employees_internal_lookup(seeder: TechnologySeeder) -> None:
    req = AgentRequirement(
        audience="employees",
        data_sensitivity="internal",
        must_ground_on=["sharepoint"],
        tools_required=["lookup"],
    )
    seeded = seeder.seed(req)
    assert seeded.profile.agent_type.value == "declarative_tenant"
    assert seeded.rationale_id == "R-LRN-001"


def test_seed_customers_external_picks_foundry(seeder: TechnologySeeder) -> None:
    req = AgentRequirement(
        audience="customers",
        must_ground_on=["web"],
        tools_required=["lookup"],
    )
    seeded = seeder.seed(req)
    assert seeded.profile.agent_type.value == "foundry_native"
    assert seeded.rationale_id == "R-LRN-003"


def test_seed_employees_writeback_picks_studio(seeder: TechnologySeeder) -> None:
    req = AgentRequirement(
        audience="employees",
        data_sensitivity="internal",
        tools_required=["lookup", "write_back", "workflow_trigger"],
    )
    seeded = seeder.seed(req)
    assert seeded.profile.agent_type.value == "copilot_studio_custom"
    assert seeded.rationale_id == "R-LRN-002"


def test_seed_restricted_customer_uses_foundry_inside_tenant(
    seeder: TechnologySeeder,
) -> None:
    req = AgentRequirement(
        audience="customers",
        data_sensitivity="restricted",
    )
    seeded = seeder.seed(req)
    assert seeded.profile.agent_type.value == "foundry_native"
    assert seeded.rationale_id == "R-LRN-004"


def test_seed_falls_back_to_default_cell(seeder: TechnologySeeder) -> None:
    req = AgentRequirement(audience="mixed")
    seeded = seeder.seed(req)
    # The default cell maps "*" audience to declarative_public.
    assert seeded.profile.agent_type.value == "declarative_public"


def test_seed_respects_tenant_channel_availability(
    seeder: TechnologySeeder,
) -> None:
    req = AgentRequirement(
        audience="employees",
        data_sensitivity="internal",
        must_ground_on=["sharepoint"],
        tools_required=["lookup"],
    )
    # No copilot SKU → m365_copilot must be filtered out.
    facts = TenantFacts(sku_part_numbers=["EMS_E5"])
    seeded = seeder.seed(req, facts)
    assert "m365_copilot" not in seeded.available_channels
    # Seeded channel must fall back to an available one.
    assert seeded.profile.channel.value in seeded.available_channels
    assert any("not available" in note for note in seeded.notes)


def test_seed_is_deterministic(seeder: TechnologySeeder) -> None:
    req = AgentRequirement(
        audience="employees",
        data_sensitivity="confidential",
        must_ground_on=["sharepoint", "graph"],
        tools_required=["lookup"],
    )
    a = seeder.seed(req)
    b = seeder.seed(req)
    assert a.profile.agent_type == b.profile.agent_type
    assert a.profile.channel == b.profile.channel
    assert a.rationale_id == b.rationale_id
