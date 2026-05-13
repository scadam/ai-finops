"""Tests for the heuristic AnomalyDetector."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from ai_finops.db import Repository
from ai_finops.domain.enums import AgentType, Channel, Meter
from ai_finops.governance import AnomalyDetector
from ai_finops.services.rate_card_service import RateCardService


def _now() -> datetime:
    return datetime.utcnow()


def _seed_agents(repo: Repository) -> None:
    repo.upsert_agent(
        agent_id="agt-zombie",
        agent_name="Zombie FT",
        agent_type=AgentType.FOUNDRY_HOSTED.value,
        channel=Channel.WEB_CHAT.value,
        environment="prod",
        fine_tuned_model_id="ft-zombie",
        agent_365_registered=False,
    )
    repo.upsert_agent(
        agent_id="agt-frontier",
        agent_name="Frontier Preview",
        agent_type=AgentType.HYBRID_STUDIO_FOUNDRY.value,
        channel=Channel.M365_COPILOT.value,
        environment="prod",
        is_frontier_preview=True,
        agent_365_registered=True,
    )
    repo.upsert_agent(
        agent_id="agt-unreg",
        agent_name="Unregistered Studio",
        agent_type=AgentType.COPILOT_STUDIO_CUSTOM.value,
        channel=Channel.M365_COPILOT.value,
        environment="prod",
        agent_365_registered=False,
    )


def _seed_token_spike(repo: Repository) -> None:
    base = _now() - timedelta(days=10)
    events = []
    for d in range(9):
        events.append(
            {
                "timestamp": base + timedelta(days=d),
                "meter": Meter.AZURE_CONSUMPTION.value,
                "agent_id": "agt-frontier",
                "tokens_input": 50_000,
                "tokens_output": 25_000,
                "model_id": "gpt-4o-mini",
                "azure_service": "azure_openai",
                "cost_actual_usd": Decimal("1.50"),
            }
        )
    events.append(
        {
            "timestamp": _now() - timedelta(hours=2),
            "meter": Meter.AZURE_CONSUMPTION.value,
            "agent_id": "agt-frontier",
            "tokens_input": 8_000_000,
            "tokens_output": 4_000_000,
            "model_id": "gpt-4o-mini",
            "azure_service": "azure_openai",
            "cost_actual_usd": Decimal("250"),
        }
    )
    repo.insert_cost_events(events, require_source=False)


def test_detect_runs_all_rules(
    repository: Repository, rate_card_service: RateCardService
) -> None:
    _seed_agents(repository)
    _seed_token_spike(repository)
    repository.insert_untagged_rows(
        [
            {
                "service_name": "Azure OpenAI",
                "resource_id": "/sub/x/openai-orphan",
                "resource_name": "openai-orphan",
                "cost_usd": Decimal("100"),
                "missing_tags": "AgentId",
            }
        ]
    )

    detector = AnomalyDetector(repository, rate_card_service)
    anomalies = detector.detect()

    detector_names = {a["detector"] for a in anomalies}
    assert "zombie_ft_model" in detector_names
    assert "frontier_preview_in_prod" in detector_names
    assert "unregistered_agent" in detector_names
    assert "untagged_spend" in detector_names
    assert "daily_token_spike" in detector_names

    for a in anomalies:
        assert a["id"].startswith("ano-")
        assert a["acknowledged"] is False
