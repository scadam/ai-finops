"""Heuristic anomaly detector for AI FinOps.

Reads aggregates from the Repository, applies a small set of deterministic
rules, and returns a list of ``AnomalyRow``-shaped dicts. Rules are kept
intentionally simple — see copilot-instructions.md §6.4 for the catalogue.
"""
from __future__ import annotations

import calendar
import logging
import statistics
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..db import Repository
from ..services.rate_card_service import RateCardService

logger = logging.getLogger(__name__)


KNOWN_AZURE_SERVICES = {
    "azure_openai",
    "ai_search",
    "foundry_tools",
    "foundry_hosted",
    "functions",
    "logic_apps",
    "storage",
    "application_insights",
    "cognitive_services",
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _agent_lookup(repo: Repository) -> dict[str, dict[str, Any]]:
    return {a["agent_id"]: a for a in repo.list_agents() if a.get("agent_id")}


class AnomalyDetector:
    """Run all detectors against the persisted ledger."""

    def __init__(self, repo: Repository, rate_cards: RateCardService) -> None:
        self._repo = repo
        self._rates = rate_cards
        self._counter = 0

    # ------------------------------------------------------------------
    def _next_id(self) -> str:
        self._counter += 1
        return f"ano-{self._counter:04d}"

    def _make(
        self,
        *,
        detector: str,
        severity: str,
        title: str,
        description: str,
        agent: dict[str, Any] | None = None,
        expected_cost_usd: Decimal = Decimal("0"),
        actual_cost_usd: Decimal = Decimal("0"),
        deviation_pct: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "id": self._next_id(),
            "detected_at": _now(),
            "severity": severity,
            "detector": detector,
            "title": title,
            "description": description,
            "affected_agent_id": (agent or {}).get("agent_id"),
            "affected_agent_name": (agent or {}).get("agent_name"),
            "expected_cost_usd": expected_cost_usd,
            "actual_cost_usd": actual_cost_usd,
            "deviation_pct": deviation_pct,
            "acknowledged": False,
        }

    # ------------------------------------------------------------------
    def detect(self) -> list[dict[str, Any]]:
        self._counter = 0
        anomalies: list[dict[str, Any]] = []
        agents = _agent_lookup(self._repo)
        anomalies.extend(self._daily_token_spike(agents))
        anomalies.extend(self._credit_burst(agents))
        anomalies.extend(self._zombie_ft_model(agents))
        anomalies.extend(self._idle_endpoint(agents))
        anomalies.extend(self._untagged_spend())
        anomalies.extend(self._grounding_cost_spike(agents))
        anomalies.extend(self._pack_exhaustion())
        anomalies.extend(self._new_ai_service())
        anomalies.extend(self._unregistered_agent(agents))
        anomalies.extend(self._frontier_preview_in_prod(agents))
        return anomalies

    # ------------------------------------------------------------------
    def _daily_token_spike(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        totals = self._repo.daily_token_totals(days=30)
        per_agent: dict[str, list[int]] = {}
        latest_by_agent: dict[str, tuple[str, int]] = {}
        for (day, agent_id), value in totals.items():
            per_agent.setdefault(agent_id, []).append(value)
            cur = latest_by_agent.get(agent_id)
            if cur is None or day > cur[0]:
                latest_by_agent[agent_id] = (day, value)
        for agent_id, series in per_agent.items():
            if len(series) < 5:
                continue
            mean = statistics.mean(series)
            std = statistics.pstdev(series) if len(series) > 1 else 0
            latest_value = latest_by_agent[agent_id][1]
            if latest_value <= 5_000_000 or latest_value <= mean + 2 * std:
                continue
            severity = "high" if latest_value > mean + 3 * std else "medium"
            out.append(
                self._make(
                    detector="daily_token_spike",
                    severity=severity,
                    title=f"Daily token spike on {agents.get(agent_id, {}).get('agent_name', agent_id)}",
                    description=(
                        f"Latest day used {latest_value:,} tokens "
                        f"(mean {mean:,.0f}, σ {std:,.0f})."
                    ),
                    agent=agents.get(agent_id),
                    expected_cost_usd=Decimal(int(mean)) / Decimal("1000000"),
                    actual_cost_usd=Decimal(latest_value) / Decimal("1000000"),
                    deviation_pct=(
                        float((latest_value - mean) / mean * 100) if mean else 0.0
                    ),
                )
            )
        return out

    def _credit_burst(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        per_agent = self._repo.credit_totals_per_agent(days=14)
        for agent_id, total in per_agent.items():
            avg_per_day = total / 14
            if avg_per_day <= 2000:
                continue
            out.append(
                self._make(
                    detector="credit_burst",
                    severity="medium",
                    title=f"Sustained credit burst on {agents.get(agent_id, {}).get('agent_name', agent_id)}",
                    description=(
                        f"Averaged {avg_per_day:,.0f} credits/day over 14 days "
                        f"(total {total:,})."
                    ),
                    agent=agents.get(agent_id),
                    expected_cost_usd=Decimal("0"),
                    actual_cost_usd=Decimal(total) * Decimal("0.01"),
                    deviation_pct=0.0,
                )
            )
        return out

    def _zombie_ft_model(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        invocations = self._repo.invocation_count_per_agent(days=7)
        idle_cost = Decimal("0")
        try:
            idle_cost = Decimal(
                str(
                    self._rates.cards.azure_infrastructure["fine_tuned_models"][
                        "deployed_idle_monthly_low"
                    ]
                )
            )
        except Exception:
            idle_cost = Decimal("100")
        out: list[dict[str, Any]] = []
        for agent_id, agent in agents.items():
            if not agent.get("fine_tuned_model_id"):
                continue
            if invocations.get(agent_id, 0) >= 7:
                continue
            out.append(
                self._make(
                    detector="zombie_ft_model",
                    severity="critical",
                    title=f"Zombie fine-tuned model: {agent.get('fine_tuned_model_id')}",
                    description=(
                        f"Agent {agent['agent_name']} has fine-tuned model "
                        f"{agent.get('fine_tuned_model_id')} but only "
                        f"{invocations.get(agent_id, 0)} invocations in 7 days."
                    ),
                    agent=agent,
                    expected_cost_usd=Decimal("0"),
                    actual_cost_usd=idle_cost,
                    deviation_pct=100.0,
                )
            )
        return out

    def _idle_endpoint(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        invocations = self._repo.invocation_count_per_agent(days=7)
        out: list[dict[str, Any]] = []
        for agent_id, agent in agents.items():
            hours = float(agent.get("hosted_hours_per_month") or 0)
            if hours <= 0:
                continue
            if invocations.get(agent_id, 0) > 0:
                continue
            out.append(
                self._make(
                    detector="idle_endpoint",
                    severity="medium",
                    title=f"Idle hosted endpoint: {agent['agent_name']}",
                    description=(
                        f"Agent has {hours:.0f} hosted hours/month allocated but "
                        f"received zero invocations in the last 7 days."
                    ),
                    agent=agent,
                )
            )
        return out

    def _untagged_spend(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self._repo.list_untagged_rows():
            out.append(
                self._make(
                    detector="untagged_spend",
                    severity="low",
                    title=f"Untagged AI spend: {row.get('service_name')}",
                    description=(
                        f"Resource {row.get('resource_name') or row.get('resource_id')} "
                        f"missing required tags ({row.get('missing_tags')})."
                    ),
                    actual_cost_usd=Decimal(str(row.get("cost_usd", "0"))),
                )
            )
        return out

    def _grounding_cost_spike(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        per_agent = self._repo.grouped_credits_by_agent_for_month()
        out: list[dict[str, Any]] = []
        for agent_id, agent in agents.items():
            if not agent.get("uses_tenant_graph"):
                continue
            credits = per_agent.get(agent_id, 0)
            if credits <= 100_000:
                continue
            out.append(
                self._make(
                    detector="grounding_cost_spike",
                    severity="medium",
                    title=f"Tenant-graph grounding cost spike on {agent['agent_name']}",
                    description=(
                        f"Agent burned {credits:,} credits this month while tenant-graph "
                        "grounding is enabled."
                    ),
                    agent=agent,
                    actual_cost_usd=Decimal(credits) * Decimal("0.01"),
                )
            )
        return out

    def _pack_exhaustion(self) -> list[dict[str, Any]]:
        summary = self._repo.cost_summary()
        credits_billed = int(summary.get("credits_billed", 0) or 0)
        if credits_billed <= 25_000:
            return []
        pack_size = 25_000
        packs = max(1, (credits_billed + pack_size - 1) // pack_size)
        capacity = packs * pack_size
        remaining_pct = max(0.0, (capacity - credits_billed) / capacity * 100)
        if remaining_pct >= 10:
            return []
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_left = days_in_month - today.day
        if days_left <= 10:
            return []
        return [
            self._make(
                detector="pack_exhaustion",
                severity="medium",
                title="Copilot Credit pack near exhaustion",
                description=(
                    f"{credits_billed:,} credits used of {capacity:,} (only "
                    f"{remaining_pct:.1f}% remaining) with {days_left} days left in month."
                ),
                actual_cost_usd=Decimal(credits_billed) * Decimal("0.01"),
            )
        ]

    def _new_ai_service(self) -> list[dict[str, Any]]:
        since = _now() - timedelta(days=7)
        out: list[dict[str, Any]] = []
        for svc in self._repo.recent_azure_services(since):
            if svc in KNOWN_AZURE_SERVICES:
                continue
            out.append(
                self._make(
                    detector="new_ai_service",
                    severity="low",
                    title=f"New Azure AI service detected: {svc}",
                    description=(
                        f"Service '{svc}' produced cost events in the last 7 days but is not "
                        "in the known catalogue."
                    ),
                )
            )
        return out

    def _unregistered_agent(self, agents: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        eligible_types = {
            "copilot_studio_custom",
            "copilot_studio_declarative",
            "foundry_native",
            "foundry_hosted",
            "hybrid_studio_foundry",
        }
        for agent in agents.values():
            if agent.get("environment") != "prod":
                continue
            if agent.get("agent_365_registered"):
                continue
            if agent.get("agent_type") not in eligible_types:
                continue
            out.append(
                self._make(
                    detector="unregistered_agent",
                    severity="medium",
                    title=f"Unregistered prod agent: {agent['agent_name']}",
                    description=(
                        f"Agent {agent['agent_name']} ({agent.get('agent_type')}) is in prod but "
                        "not registered with Agent 365."
                    ),
                    agent=agent,
                )
            )
        return out

    def _frontier_preview_in_prod(
        self, agents: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for agent in agents.values():
            if not agent.get("is_frontier_preview"):
                continue
            if agent.get("environment") != "prod":
                continue
            out.append(
                self._make(
                    detector="frontier_preview_in_prod",
                    severity="high",
                    title=f"Frontier preview model in prod: {agent['agent_name']}",
                    description=(
                        f"Agent {agent['agent_name']} is using a frontier preview model in prod "
                        "where SLAs are not guaranteed."
                    ),
                    agent=agent,
                )
            )
        return out
