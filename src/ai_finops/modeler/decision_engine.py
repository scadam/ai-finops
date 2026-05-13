"""Pure-function decision engine — `(candidate, tenant_facts) → DecisionScore`.

Every input value and computed sub-score is captured in
``DecisionScore.inputs`` so a reviewer can reproduce the result by hand.
This is what makes the engine impartial — see Part 2 §4 of the plan.

No external knowledge calls. No clock or random dependency.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from ..domain.enums import AgentType, Channel
from ..domain.models import AgentProfile, InteractionProfile
from ..services.cost_calculator import CostCalculator
from .requirement import AgentRequirement
from .seeder import SeededDesign, TechnologySeeder, TenantFacts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
@dataclass
class DecisionScore:
    fit: float = 0.0
    cost_efficiency: float = 0.0
    risk: float = 0.0
    compliance: float = 0.0
    total: float = 0.0
    monthly_usd: Decimal = Decimal("0")
    inputs: dict[str, Any] = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)


@dataclass
class CandidateRanking:
    profile: AgentProfile
    usage: InteractionProfile
    score: DecisionScore


# ---------------------------------------------------------------------
class DecisionEngine:
    """Deterministic candidate scorer."""

    DEFAULT_WEIGHTS = {"fit": 0.4, "cost_efficiency": 0.3, "risk": 0.15, "compliance": 0.15}
    DEFAULT_CAPS = {"cost_efficiency_max_usd": 100000.0, "risk_max_alerts": 5}

    def __init__(
        self,
        cost_calculator: CostCalculator,
        seeder: TechnologySeeder,
        weights_path: Path | str | None = "config/modeler/decision_weights.yaml",
        weights: dict[str, float] | None = None,
        caps: dict[str, float] | None = None,
    ) -> None:
        self._calc = cost_calculator
        self._seeder = seeder
        if weights is None:
            weights, caps = self._load_weights(weights_path)
        self._weights = self._normalise_weights(weights)
        self._caps = {**self.DEFAULT_CAPS, **(caps or {})}

    # --------------------------------------------------------------
    @staticmethod
    def _load_weights(
        path: Path | str | None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        if not path:
            return DecisionEngine.DEFAULT_WEIGHTS.copy(), DecisionEngine.DEFAULT_CAPS.copy()
        p = Path(path)
        if not p.exists():
            logger.warning("decision_weights.yaml not found at %s; using defaults", p)
            return DecisionEngine.DEFAULT_WEIGHTS.copy(), DecisionEngine.DEFAULT_CAPS.copy()
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        weights = {k: float(v) for k, v in (data.get("weights") or {}).items()}
        caps = {k: float(v) for k, v in (data.get("caps") or {}).items()}
        return weights or DecisionEngine.DEFAULT_WEIGHTS.copy(), caps

    @staticmethod
    def _normalise_weights(weights: dict[str, float]) -> dict[str, float]:
        total = sum(weights.values())
        if total <= 0:
            logger.warning("decision weights sum to %s; falling back to defaults", total)
            return DecisionEngine.DEFAULT_WEIGHTS.copy()
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "decision weights sum to %.4f, renormalising (was %s)", total, weights
            )
            return {k: v / total for k, v in weights.items()}
        return weights

    # --------------------------------------------------------------
    def score(
        self,
        profile: AgentProfile,
        usage: InteractionProfile,
        req: AgentRequirement,
        facts: TenantFacts | None = None,
    ) -> DecisionScore:
        breakdown = self._calc.estimate(profile, usage)
        monthly_usd = Decimal(str(breakdown.total_monthly_usd))
        fit = self._fit(profile, req)
        cost_eff = self._cost_efficiency(monthly_usd)
        risk = self._risk(profile, facts)
        compliance = self._compliance(profile, req)
        total = (
            self._weights["fit"] * fit
            + self._weights["cost_efficiency"] * cost_eff
            + self._weights["risk"] * risk
            + self._weights["compliance"] * compliance
        )
        score = DecisionScore(
            fit=round(fit, 4),
            cost_efficiency=round(cost_eff, 4),
            risk=round(risk, 4),
            compliance=round(compliance, 4),
            total=round(total, 4),
            monthly_usd=monthly_usd,
            inputs={
                "weights": dict(self._weights),
                "caps": dict(self._caps),
                "agent_type": profile.agent_type.value,
                "channel": profile.channel.value,
                "must_ground_on": list(req.must_ground_on),
                "tools_required": list(req.tools_required),
                "data_sensitivity": req.data_sensitivity,
                "risk_alerts_high": getattr(facts, "risk_alert_count", 0) if facts else 0,
                "is_frontier_preview": profile.is_frontier_preview,
            },
            rationale=self._explain(profile, req, fit, cost_eff, risk, compliance),
        )
        return score

    # --------------------------------------------------------------
    def _fit(self, profile: AgentProfile, req: AgentRequirement) -> float:
        caps = self._seeder.capabilities.get(profile.agent_type.value) or {}
        supported_grounding = {g.lower() for g in caps.get("must_ground_on", [])}
        supported_tools = {t.lower() for t in caps.get("tools_required", [])}
        required_grounding = {g.lower() for g in req.must_ground_on}
        required_tools = {t.lower() for t in req.tools_required}
        denom = len(required_grounding) + len(required_tools)
        if denom == 0:
            # No requirements stated → trivially a perfect fit.
            return 1.0
        matched = len(required_grounding & supported_grounding) + len(
            required_tools & supported_tools
        )
        return matched / denom

    def _cost_efficiency(self, monthly_usd: Decimal) -> float:
        cap = float(self._caps.get("cost_efficiency_max_usd", 100000.0))
        if cap <= 0:
            return 0.0
        # 1.0 at $0/mo, 0.0 at cap or above.
        usd = float(monthly_usd)
        return max(0.0, 1.0 - min(usd, cap) / cap)

    def _risk(self, profile: AgentProfile, facts: TenantFacts | None) -> float:
        cap = float(self._caps.get("risk_max_alerts", 5))
        alerts = float(getattr(facts, "risk_alert_count", 0)) if facts else 0.0
        alert_penalty = min(alerts, cap) / cap if cap else 0.0
        preview_penalty = 0.25 if profile.is_frontier_preview else 0.0
        # 1.0 means "low risk".
        return max(0.0, 1.0 - alert_penalty - preview_penalty)

    def _compliance(self, profile: AgentProfile, req: AgentRequirement) -> float:
        eligible = {
            s.lower()
            for s in self._seeder.compliance_sensitivity.get(profile.agent_type.value, [])
        }
        return 1.0 if req.data_sensitivity.lower() in eligible else 0.0

    @staticmethod
    def _explain(
        profile: AgentProfile,
        req: AgentRequirement,
        fit: float,
        cost: float,
        risk: float,
        compliance: float,
    ) -> list[str]:
        return [
            f"fit={fit:.2f} from must_ground_on={req.must_ground_on}, "
            f"tools_required={req.tools_required}",
            f"cost_efficiency={cost:.2f} (1 - cost/cap)",
            f"risk={risk:.2f} (1 - alert_penalty - preview_penalty)",
            f"compliance={compliance:.2f} ({'pass' if compliance else 'fail'} sensitivity gate)",
            f"agent_type={profile.agent_type.value}, channel={profile.channel.value}",
        ]

    # --------------------------------------------------------------
    def alternatives(
        self,
        seeded: SeededDesign,
        req: AgentRequirement,
        facts: TenantFacts | None = None,
        agent_types: tuple[AgentType, ...] | None = None,
        channels: tuple[Channel, ...] | None = None,
    ) -> list[CandidateRanking]:
        """Combinatorially permute (agent_type × channel) and rank by total."""
        from dataclasses import replace

        agent_types = agent_types or tuple(AgentType)
        if channels is None:
            avail = seeded.available_channels or [c.value for c in Channel]
            channels = tuple(Channel(c) for c in avail if c in {ch.value for ch in Channel})
        seen: set[tuple[str, str]] = set()
        candidates: list[CandidateRanking] = []
        for at in agent_types:
            for ch in channels:
                key = (at.value, ch.value)
                if key in seen:
                    continue
                seen.add(key)
                profile = replace(seeded.profile, agent_type=at, channel=ch)
                score = self.score(profile, seeded.usage, req, facts)
                candidates.append(
                    CandidateRanking(profile=profile, usage=seeded.usage, score=score)
                )
        candidates.sort(key=lambda c: c.score.total, reverse=True)
        return candidates
