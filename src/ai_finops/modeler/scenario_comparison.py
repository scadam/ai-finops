"""Side-by-side comparison across agent technology choices.

See copilot-instructions.md §6.3 / §8.3.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal

from ..domain.enums import AgentType
from ..domain.models import AgentProfile, CostBreakdown, InteractionProfile
from ..services.cost_calculator import CostCalculator

# Default catalogue of realistic agent_types to compare.
DEFAULT_AGENT_TYPES: tuple[AgentType, ...] = (
    AgentType.DECLARATIVE_INSTRUCTION,
    AgentType.DECLARATIVE_TENANT,
    AgentType.COPILOT_STUDIO_CUSTOM,
    AgentType.FOUNDRY_NATIVE,
    AgentType.FOUNDRY_HOSTED,
    AgentType.HYBRID_STUDIO_FOUNDRY,
)


@dataclass
class ScenarioResult:
    profile: AgentProfile
    breakdown: CostBreakdown


@dataclass
class ScenarioReport:
    results: list[ScenarioResult] = field(default_factory=list)
    cheapest: ScenarioResult | None = None
    recommendation: str = ""
    notes: list[str] = field(default_factory=list)


class ScenarioComparison:
    """Compare multiple agent design options side-by-side."""

    def __init__(self, calculator: CostCalculator) -> None:
        self._calc = calculator

    def compare(
        self,
        base_profile: AgentProfile,
        usage: InteractionProfile,
        agent_types: tuple[AgentType, ...] | None = None,
        period_months: int = 1,
    ) -> ScenarioReport:
        agent_types = agent_types or DEFAULT_AGENT_TYPES
        results: list[ScenarioResult] = []
        for agent_type in agent_types:
            profile = replace(base_profile, agent_type=agent_type)
            breakdown = self._calc.estimate(
                profile, usage, period_months=period_months, scenario_name=agent_type.value
            )
            results.append(ScenarioResult(profile=profile, breakdown=breakdown))

        results.sort(key=lambda r: r.breakdown.total_monthly_usd)
        cheapest = results[0] if results else None
        recommendation = self._build_recommendation(cheapest, results)
        return ScenarioReport(results=results, cheapest=cheapest, recommendation=recommendation)

    @staticmethod
    def _build_recommendation(
        cheapest: ScenarioResult | None,
        all_results: list[ScenarioResult],
    ) -> str:
        if not cheapest:
            return ""
        lines = [
            f"Cheapest viable option: {cheapest.profile.agent_type.value} "
            f"at ${cheapest.breakdown.total_monthly_usd}/month."
        ]
        if cheapest.breakdown.b2e_zero_rated:
            lines.append("B2E zero-rating applied for licensed users on M365 channel.")
        if cheapest.breakdown.total_monthly_usd == Decimal("0"):
            lines.append("This scenario is in the declarative free tier — $0 for ALL users.")
        if len(all_results) > 1:
            second = all_results[1]
            delta = second.breakdown.total_monthly_usd - cheapest.breakdown.total_monthly_usd
            lines.append(
                f"Next-cheapest option ({second.profile.agent_type.value}) is "
                f"${delta}/month more expensive."
            )
        return " ".join(lines)
