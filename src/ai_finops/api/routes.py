"""HTTP routes for the AI FinOps backend.

Implements the endpoints listed in copilot-instructions.md §7. Endpoints
that depend on persistent storage (cost ledger, anomalies, budgets) are
implemented as in-memory stubs that return well-formed empty payloads —
hook them up to Azure SQL once the database layer is in place.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import (
    AgentProfile,
    CostBreakdown,
    InteractionProfile,
    OptimisationRecommendation,
)
from ..modeler.scenario_comparison import ScenarioComparison
from ..optimisation.recommender import OptimisationRecommender
from ..services.cost_calculator import CostCalculator
from ..services.rate_card_service import RateCardService
from .schemas import (
    AgentProfileIn,
    CompareRequest,
    CompareResponse,
    CostBreakdownOut,
    EstimateRequest,
    HealthResponse,
    InteractionProfileIn,
    OptimisationOut,
)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def _rates(request: Request) -> RateCardService:
    return request.app.state.rate_card_service


def _calculator(request: Request) -> CostCalculator:
    return request.app.state.cost_calculator


def _scenarios(request: Request) -> ScenarioComparison:
    return request.app.state.scenario_comparison


def _recommender(request: Request) -> OptimisationRecommender:
    return request.app.state.optimisation_recommender


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------
def _profile_from_in(profile_in: AgentProfileIn) -> AgentProfile:
    return AgentProfile(**profile_in.model_dump())


def _usage_from_in(usage_in: InteractionProfileIn) -> InteractionProfile:
    return InteractionProfile(**usage_in.model_dump())


def _opt_to_out(rec: OptimisationRecommendation) -> OptimisationOut:
    return OptimisationOut(
        category=rec.category,
        title=rec.title,
        description=rec.description,
        monthly_saving_usd=str(rec.monthly_saving_usd),
        implementation_effort=rec.implementation_effort,
        confidence=rec.confidence,
        before_cost_usd=str(rec.before_cost_usd),
        after_cost_usd=str(rec.after_cost_usd),
        evidence=rec.evidence,
        action_url=rec.action_url,
        agent_id=rec.agent_id,
    )


def _breakdown_to_out(b: CostBreakdown) -> CostBreakdownOut:
    return CostBreakdownOut(
        scenario_name=b.scenario_name,
        period_months=b.period_months,
        utilisation_band=b.utilisation_band,
        confidence=b.confidence,
        license_cost_total_usd=str(b.license_cost_total_usd),
        license_detail=b.license_detail,
        credits_charged=b.credits_charged,
        credits_zero_rated=b.credits_zero_rated,
        credits_shadow=b.credits_shadow,
        credits_cost_payg_usd=str(b.credits_cost_payg_usd),
        credits_cost_pack_usd=str(b.credits_cost_pack_usd),
        credits_packs_required=b.credits_packs_required,
        credits_recommendation=b.credits_recommendation,
        credits_detail=b.credits_detail,
        b2e_zero_rated=b.b2e_zero_rated,
        tokens_monthly=b.tokens_monthly,
        azure_openai_cost_usd=str(b.azure_openai_cost_usd),
        foundry_tools_cost_usd=str(b.foundry_tools_cost_usd),
        ai_search_cost_usd=str(b.ai_search_cost_usd),
        hosted_agent_compute_usd=str(b.hosted_agent_compute_usd),
        azure_total_usd=str(b.azure_total_usd),
        total_monthly_usd=str(b.total_monthly_usd),
        total_annual_usd=str(b.total_annual_usd),
        cost_per_interaction_usd=str(b.cost_per_interaction_usd),
        cost_per_active_user_monthly_usd=str(b.cost_per_active_user_monthly_usd),
        low_estimate_usd=str(b.low_estimate_usd),
        high_estimate_usd=str(b.high_estimate_usd),
        potential_savings_usd=str(b.potential_savings_usd),
        optimisation_recommendations=[_opt_to_out(r) for r in b.optimisation_recommendations],
        notes=b.notes,
    )


# ---------------------------------------------------------------------------
# Health + rate cards
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(request: Request) -> HealthResponse:
    rates = _rates(request)
    from ..config import get_settings
    return HealthResponse(status="ok", env=get_settings().env, rate_cards=rates.status())


@router.get("/rate-cards", tags=["rate-cards"])
def get_rate_cards(rates: RateCardService = Depends(_rates)) -> dict[str, Any]:
    cards = rates.cards
    return {
        "per_seat": cards.per_seat,
        "copilot_credits": cards.copilot_credits,
        "azure_openai": cards.azure_openai,
        "foundry_agent_service": cards.foundry_agent_service,
        "ai_search": cards.ai_search,
        "azure_infrastructure": cards.azure_infrastructure,
    }


@router.get("/rate-cards/refresh-status", tags=["rate-cards"])
def rate_cards_refresh_status(rates: RateCardService = Depends(_rates)) -> list[dict[str, Any]]:
    return rates.status()


@router.post("/rate-cards/reload", tags=["rate-cards"])
def rate_cards_reload(rates: RateCardService = Depends(_rates)) -> dict[str, Any]:
    rates.load()
    return {"status": "reloaded", "cards": rates.status()}


# ---------------------------------------------------------------------------
# What-if modeller
# ---------------------------------------------------------------------------
@router.post("/agents/{agent_id}/estimate", response_model=CostBreakdownOut, tags=["modeler"])
def agent_estimate(
    agent_id: str,
    payload: EstimateRequest,
    calculator: CostCalculator = Depends(_calculator),
    recommender: OptimisationRecommender = Depends(_recommender),
) -> CostBreakdownOut:
    profile_in = payload.profile
    if not profile_in.agent_id:
        profile_in.agent_id = agent_id
    profile = _profile_from_in(profile_in)
    usage = _usage_from_in(payload.usage)
    breakdown = calculator.estimate(
        profile, usage, period_months=payload.period_months, scenario_name=payload.scenario_name
    )
    recs = recommender.recommend(profile, breakdown)
    breakdown.optimisation_recommendations = recs
    breakdown.potential_savings_usd = sum(
        (r.monthly_saving_usd for r in recs), Decimal("0")
    )
    return _breakdown_to_out(breakdown)


@router.post("/scenarios/compare", response_model=CompareResponse, tags=["modeler"])
def scenarios_compare(
    payload: CompareRequest,
    scenarios: ScenarioComparison = Depends(_scenarios),
) -> CompareResponse:
    profile = _profile_from_in(payload.base_profile)
    usage = _usage_from_in(payload.usage)
    report = scenarios.compare(
        profile, usage, agent_types=tuple(payload.agent_types) if payload.agent_types else None,
        period_months=payload.period_months,
    )
    results = [_breakdown_to_out(r.breakdown) for r in report.results]
    cheapest = _breakdown_to_out(report.cheapest.breakdown) if report.cheapest else None
    return CompareResponse(cheapest=cheapest, recommendation=report.recommendation, results=results)


# ---------------------------------------------------------------------------
# Cost ledger / agents / optimisations / governance — stub responses.
# Hook these to Azure SQL queries in a future iteration.
# ---------------------------------------------------------------------------
@router.get("/agents", tags=["agents"])
def list_agents() -> list[dict[str, Any]]:
    return []


@router.get("/agents/{agent_id}", tags=["agents"])
def get_agent(agent_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found (no DB in this build)")


@router.get("/cost/ledger", tags=["cost"])
def cost_ledger(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    return {"items": [], "limit": limit, "offset": offset, "total": 0}


@router.get("/cost/summary", tags=["cost"])
def cost_summary() -> dict[str, Any]:
    return {"by_meter": {"per_seat": "0", "copilot_credits": "0", "azure_consumption": "0"}}


@router.get("/cost/trends", tags=["cost"])
def cost_trends() -> dict[str, Any]:
    return {"series": []}


@router.get("/optimisations", tags=["optimisations"])
def list_optimisations() -> list[dict[str, Any]]:
    return []


@router.get("/licenses", tags=["governance"])
def licenses_summary() -> dict[str, Any]:
    return {"assigned": 0, "active_7d": 0, "active_30d": 0, "shadow_credits": 0}


@router.get("/credits", tags=["governance"])
def credits_summary() -> dict[str, Any]:
    return {"by_agent": [], "total_charged": 0, "total_shadow": 0}


@router.get("/budgets", tags=["governance"])
def list_budgets() -> list[dict[str, Any]]:
    return []


@router.get("/anomalies", tags=["governance"])
def list_anomalies() -> list[dict[str, Any]]:
    return []


@router.get("/reports/executive-summary", tags=["reports"])
def executive_summary() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_ai_spend_usd": "0",
        "by_meter": {},
        "top_agents": [],
        "top_optimisations": [],
    }


@router.get("/reports/focus-export", tags=["reports"])
def focus_export() -> dict[str, Any]:
    return {"format": "FOCUS 1.1", "rows": []}
