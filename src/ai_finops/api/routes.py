"""HTTP routes for the AI FinOps backend.

Implements the endpoints listed in copilot-instructions.md §7. Most cost,
agent, optimisation and governance endpoints query the SQLAlchemy
``Repository`` exposed via ``app.state.repository``.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ..db import Repository
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
    BudgetIn,
    CompareRequest,
    CompareResponse,
    CostBreakdownOut,
    EstimateRequest,
    HealthResponse,
    InteractionProfileIn,
    OptimisationOut,
)

logger = logging.getLogger(__name__)
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


def _repo(request: Request) -> Repository:
    return request.app.state.repository


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


def _rate_card_status(rates: RateCardService) -> list[dict[str, Any]]:
    return [
        {
            "name": s["name"],
            "last_refreshed": s["loaded_at"],
            "is_stale": s["is_stale"],
            "effective_date": s["effective_date"],
            "source_url": s.get("source_path", ""),
        }
        for s in rates.status()
    ]


# ---------------------------------------------------------------------------
# Health + rate cards
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(request: Request) -> HealthResponse:
    rates = _rates(request)
    from ..config import get_settings

    return HealthResponse(
        status="ok", env=get_settings().env, rate_cards=_rate_card_status(rates)
    )


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
    return _rate_card_status(rates)


@router.post("/rate-cards/reload", tags=["rate-cards"])
def rate_cards_reload(rates: RateCardService = Depends(_rates)) -> dict[str, Any]:
    rates.load()
    return {"status": "reloaded", "cards": _rate_card_status(rates)}


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
# Agents
# ---------------------------------------------------------------------------
@router.get("/agents", tags=["agents"])
def list_agents(
    environment: str | None = None,
    cost_center: str | None = None,
    agent_type: str | None = None,
    repo: Repository = Depends(_repo),
) -> list[dict[str, Any]]:
    return repo.list_agents(environment=environment, cost_center=cost_center, agent_type=agent_type)


@router.get("/agents/{agent_id}", tags=["agents"])
def get_agent(agent_id: str, repo: Repository = Depends(_repo)) -> dict[str, Any]:
    row = repo.get_agent(agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return row


# ---------------------------------------------------------------------------
# Cost ledger / summary / trends
# ---------------------------------------------------------------------------
@router.get("/cost/ledger", tags=["cost"])
def cost_ledger(
    limit: int = 100,
    offset: int = 0,
    meter: str | None = None,
    agent_id: str | None = None,
    cost_center: str | None = None,
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    return repo.list_cost_events(
        limit=limit, offset=offset, meter=meter, agent_id=agent_id, cost_center=cost_center
    )


@router.get("/cost/summary", tags=["cost"])
def cost_summary(repo: Repository = Depends(_repo)) -> dict[str, Any]:
    return repo.cost_summary()


@router.get("/cost/trends", tags=["cost"])
def cost_trends(months: int = 6, repo: Repository = Depends(_repo)) -> list[dict[str, Any]]:
    return repo.cost_trends(months=months)


# ---------------------------------------------------------------------------
# Optimisations
# ---------------------------------------------------------------------------
@router.get("/optimisations", tags=["optimisations"])
def list_optimisations(
    category: str | None = None,
    effort: str | None = None,
    min_saving: float | None = None,
    include_dismissed: bool = False,
    repo: Repository = Depends(_repo),
) -> list[dict[str, Any]]:
    return repo.list_optimisations(
        category=category,
        effort=effort,
        min_saving=Decimal(str(min_saving)) if min_saving is not None else None,
        include_dismissed=include_dismissed,
    )


@router.post("/optimisations/{opt_id}/dismiss", tags=["optimisations"])
def dismiss_optimisation(
    opt_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    reason = str(body.get("reason", ""))
    row = repo.dismiss_optimisation(opt_id, reason)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Optimisation {opt_id} not found")
    return row


# ---------------------------------------------------------------------------
# Governance — licenses / credits / budgets / anomalies
# ---------------------------------------------------------------------------
@router.get("/licenses", tags=["governance"])
def licenses_summary(repo: Repository = Depends(_repo)) -> list[dict[str, Any]]:
    return repo.license_summary()


@router.get("/credits", tags=["governance"])
def credits_summary(repo: Repository = Depends(_repo)) -> dict[str, Any]:
    return repo.credit_usage()


@router.get("/budgets", tags=["governance"])
def list_budgets(repo: Repository = Depends(_repo)) -> list[dict[str, Any]]:
    return repo.list_budgets()


@router.post("/budgets", tags=["governance"])
def create_budget(
    payload: BudgetIn, repo: Repository = Depends(_repo)
) -> dict[str, Any]:
    return repo.create_budget(**payload.model_dump())


@router.get("/anomalies", tags=["governance"])
def list_anomalies(
    severity: str | None = None,
    acknowledged: bool | None = None,
    repo: Repository = Depends(_repo),
) -> list[dict[str, Any]]:
    return repo.list_anomalies(severity=severity, acknowledged=acknowledged)


@router.post("/anomalies/{anomaly_id}/acknowledge", tags=["governance"])
def acknowledge_anomaly(
    anomaly_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    action = str(body.get("action", ""))
    acknowledged_by = str(body.get("by", ""))
    row = repo.acknowledge_anomaly(anomaly_id, action=action, by=acknowledged_by)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")
    return row


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@router.get("/reports/executive-summary", tags=["reports"])
def executive_summary(repo: Repository = Depends(_repo)) -> dict[str, Any]:
    summary = repo.cost_summary()
    top_optimisations = repo.list_optimisations()[:3]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_ai_spend_usd": summary.get("total_monthly_usd", "0"),
        "by_meter": summary.get("by_meter", {}),
        "top_optimisations": top_optimisations,
        "summary": summary,
    }


FOCUS_COLUMNS = [
    "BillingPeriodStart",
    "ChargePeriodStart",
    "BilledCost",
    "EffectiveCost",
    "ServiceName",
    "ServiceCategory",
    "ResourceId",
    "ResourceName",
    "ResourceType",
    "Tags.AgentId",
    "Tags.CostCenter",
    "Tags.Owner",
    "Tags.Environment",
    "UsageQuantity",
    "UsageUnit",
]


@router.get("/reports/focus-export", tags=["reports"])
def focus_export(
    download: bool = False,
    repo: Repository = Depends(_repo),
):
    rows = repo.focus_rows()
    if not download:
        return {
            "format": "FOCUS 1.1",
            "row_count": len(rows),
            "columns": FOCUS_COLUMNS,
        }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FOCUS_COLUMNS)
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in FOCUS_COLUMNS})
    csv_bytes = buf.getvalue().encode("utf-8")
    filename = f"focus-export-{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
