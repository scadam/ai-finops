"""Round-trip tests against the SQLAlchemy Repository."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ai_finops.db import Repository
from ai_finops.domain.enums import AgentType, Channel, Meter


def _agent_fields(agent_id: str = "agt-test") -> dict:
    return {
        "agent_id": agent_id,
        "agent_name": "Test Agent",
        "agent_type": AgentType.COPILOT_STUDIO_CUSTOM.value,
        "channel": Channel.M365_COPILOT.value,
        "owner": "tester@example.com",
        "cost_center": "TEST-001",
        "environment": "prod",
        "licensed_user_count": 100,
    }


def test_agent_upsert_and_lookup(repository: Repository) -> None:
    repository.upsert_agent(**_agent_fields())
    agents = repository.list_agents()
    assert len(agents) == 1
    assert repository.get_agent("agt-test")["agent_name"] == "Test Agent"


def test_cost_summary_and_trends(repository: Repository) -> None:
    repository.upsert_agent(**_agent_fields())
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1, 12)
    repository.insert_cost_events(
        [
            {
                "timestamp": month_start,
                "meter": Meter.PER_SEAT.value,
                "agent_id": "agt-test",
                "sku_id": "M365_COPILOT",
                "assigned_users": 100,
                "active_users_7d": 70,
                "cost_actual_usd": Decimal("3000"),
            },
            {
                "timestamp": month_start,
                "meter": Meter.COPILOT_CREDITS.value,
                "agent_id": "agt-test",
                "credits_consumed": 5000,
                "cost_actual_usd": Decimal("50"),
            },
            {
                "timestamp": month_start,
                "meter": Meter.AZURE_CONSUMPTION.value,
                "agent_id": "agt-test",
                "tokens_input": 100_000,
                "tokens_output": 50_000,
                "model_id": "gpt-4o-mini",
                "azure_service": "azure_openai",
                "cost_actual_usd": Decimal("12.34"),
            },
        ]
    )
    summary = repository.cost_summary()
    assert Decimal(summary["total_monthly_usd"]) == Decimal("3062.34")
    assert summary["credits_billed"] == 5000
    assert summary["top_model"] == "gpt-4o-mini"

    trends = repository.cost_trends(months=3)
    assert len(trends) == 3
    assert Decimal(trends[-1]["total_cost_usd"]) > 0


def test_optimisation_filters(repository: Repository) -> None:
    repository.replace_recommendations(
        "agt-test",
        [
            {
                "category": "model_downshift",
                "title": "Downshift to mini",
                "description": "Use cheaper model",
                "monthly_saving_usd": Decimal("500"),
                "implementation_effort": "low",
                "confidence": 0.8,
                "before_cost_usd": Decimal("1000"),
                "after_cost_usd": Decimal("500"),
                "evidence": "n/a",
            },
            {
                "category": "prompt_caching",
                "title": "Enable caching",
                "description": "10% savings",
                "monthly_saving_usd": Decimal("50"),
                "implementation_effort": "medium",
                "confidence": 0.6,
                "before_cost_usd": Decimal("500"),
                "after_cost_usd": Decimal("450"),
                "evidence": "n/a",
            },
        ],
    )
    high = repository.list_optimisations(min_saving=Decimal("100"))
    assert [r["category"] for r in high] == ["model_downshift"]
    by_effort = repository.list_optimisations(effort="medium")
    assert len(by_effort) == 1
