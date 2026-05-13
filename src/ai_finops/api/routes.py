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
from ..domain.enums import AgentType, Channel
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


# =====================================================================
# Plug-and-play ingestion: data-sources health + admin run
# =====================================================================
@router.get("/data-sources")
def list_data_sources(
    request: Request,
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    """List every plug-and-play puller, last-success time, and SDK call.

    Powers the Governance tab "data sources" panel — see Part 1 §4 of the plan.
    """
    from ..config import get_settings
    from ..ingestion import (
        Agent365DirectoryPuller,
        AzureInventoryPuller,
        CostManagementPuller,
        DefenderPuller,
        EntraDirectoryPuller,
        GraphCreditsPuller,
        GraphLicensePuller,
        PowerPlatformPuller,
        PurviewPuller,
    )

    settings = get_settings()
    flags = settings.feature_flags()
    catalogue = {
        "agent365": Agent365DirectoryPuller,
        "entra_directory": EntraDirectoryPuller,
        "purview": PurviewPuller,
        "defender": DefenderPuller,
        "power_platform": PowerPlatformPuller,
        "azure_inventory": AzureInventoryPuller,
        "cost_management": CostManagementPuller,
        "graph_credits": GraphCreditsPuller,
        "graph_licenses": GraphLicensePuller,
    }
    last_runs = repo.latest_ingestion_per_job()
    sources = []
    for job, cls in catalogue.items():
        last = last_runs.get(job, {})
        sources.append({
            "job": job,
            "enabled": bool(flags.get(job, False)),
            "sdk_call": getattr(cls, "sdk_call", ""),
            "source_system": getattr(cls, "source_system", job),
            "last_status": last.get("status"),
            "last_started_at": (
                last.get("started_at").isoformat() if last.get("started_at") else None
            ),
            "last_finished_at": (
                last.get("finished_at").isoformat() if last.get("finished_at") else None
            ),
            "last_rows_in": last.get("rows_in") or 0,
            "last_rows_written": last.get("rows_written") or 0,
            "last_error": last.get("error"),
        })
    return {"sources": sources, "tenant_id": settings.azure_tenant_id or settings.tenant_id}


@router.get("/ingestion/runs")
def ingestion_runs(
    repo: Repository = Depends(_repo),
    limit: int = 50,
) -> dict[str, Any]:
    """Recent ingestion-run audit rows (newest first)."""
    rows = repo.list_ingestion_runs(limit=limit)
    return {
        "runs": [
            {
                **r,
                "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
            }
            for r in rows
        ]
    }


@router.post("/ingestion/run")
def trigger_ingestion(
    request: Request,
    repo: Repository = Depends(_repo),
    body: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Fan out to enabled pullers (admin endpoint).

    The body MAY pass ``{"jobs": ["agent365", ...]}`` to limit which sources
    run; otherwise all flag-enabled sources run. Pullers themselves are
    constructed by :class:`MicrosoftAuthFactory` (when the host wires it onto
    ``app.state.auth_factory``); when no factory is configured this endpoint
    returns the *would-run* plan instead — keeps the API testable without
    real credentials.
    """
    from ..config import get_settings
    from ..ingestion import IngestionRunner

    settings = get_settings()
    flags = settings.feature_flags()
    requested = body.get("jobs") or [job for job, on in flags.items() if on]

    factory = getattr(request.app.state, "auth_factory", None)
    if factory is None:
        # Plan mode — list the jobs that would run with their SDK calls.
        return {
            "mode": "plan",
            "would_run": [
                {"job": job, "enabled": flags.get(job, False)}
                for job in requested
            ],
            "message": (
                "MicrosoftAuthFactory not wired into app.state. "
                "Configure AZURE_TENANT_ID + run with Managed Identity to execute."
            ),
        }

    runner = IngestionRunner(repo)
    jobs: dict[str, Any] = {}
    builders = factory.build_pullers(jobs=requested, settings=settings)
    for job, kwargs in builders.items():
        if not flags.get(job, False) and job in flags:
            continue
        jobs[job] = kwargs
    results = runner.run_enabled(jobs)
    return {
        "mode": "executed",
        "results": [
            {
                "job": r.job,
                "sdk_call": r.sdk_call,
                "status": r.status,
                "rows_in": r.rows_in,
                "rows_written": r.rows_written,
                "untagged_rows": r.untagged_rows,
                "error": r.error,
            }
            for r in results
        ],
    }


# =====================================================================
# Modeller (Part 2)
# =====================================================================
def _seeder(request: Request):
    seeder = getattr(request.app.state, "technology_seeder", None)
    if seeder is None:
        from pathlib import Path

        from ..config import get_settings
        from ..modeler import TechnologySeeder

        path = Path(get_settings().modeler_config_dir) / "decision_matrix.yaml"
        seeder = TechnologySeeder(matrix_path=path)
        request.app.state.technology_seeder = seeder
    return seeder


def _engine(request: Request):
    engine = getattr(request.app.state, "decision_engine", None)
    if engine is None:
        from pathlib import Path

        from ..config import get_settings
        from ..modeler import DecisionEngine

        weights = Path(get_settings().modeler_config_dir) / "decision_weights.yaml"
        engine = DecisionEngine(
            cost_calculator=request.app.state.cost_calculator,
            seeder=_seeder(request),
            weights_path=weights,
        )
        request.app.state.decision_engine = engine
    return engine


def _facts(request: Request, repo: Repository):
    from ..modeler.seeder import TenantFacts

    return TenantFacts.from_repository(repo)


def _profile_to_dict(profile: AgentProfile) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in profile.__dict__.items():
        if hasattr(value, "value"):
            out[key] = value.value
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, Decimal):
            out[key] = str(value)
        else:
            out[key] = value
    return out


@router.post("/modeler/requirements")
def create_requirement(
    body: dict[str, Any] = Body(...),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    """Capture a requirement.

    Body may be:
    * ``{"description": "..."}`` — parsed by RequirementParser, OR
    * ``{"description": "...", "audience": "...", ...}`` — already structured
      fields override parser output.
    """
    from ..modeler import parse_free_text

    description = str(body.get("description") or "")
    if not description and not body.get("audience"):
        raise HTTPException(status_code=400, detail="description or structured fields required")
    parsed = parse_free_text(description) if description else None
    overrides = {k: v for k, v in body.items() if k != "description" and v is not None}
    if parsed is None:
        from ..modeler import AgentRequirement

        parsed = AgentRequirement(description=description)
    for k, v in overrides.items():
        if hasattr(parsed, k):
            setattr(parsed, k, v)
    saved = repo.create_requirement(**parsed.to_db_fields())
    return {
        "id": parsed.id,
        "parsed": {
            "audience": parsed.audience,
            "audience_size": parsed.audience_size,
            "data_sensitivity": parsed.data_sensitivity,
            "must_ground_on": parsed.must_ground_on,
            "tools_required": parsed.tools_required,
            "latency_target_ms": parsed.latency_target_ms,
            "compliance_constraints": parsed.compliance_constraints,
            "expected_interactions_per_user_per_month":
                parsed.expected_interactions_per_user_per_month,
        },
        "stored": {**saved, "created_at": saved.get("created_at").isoformat() if saved.get("created_at") else None},
    }


@router.post("/modeler/seed")
def modeler_seed(
    request: Request,
    body: dict[str, Any] = Body(...),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    """Given a requirement_id, return seeded design + ranked alternatives."""
    import uuid

    from ..modeler import AgentRequirement

    requirement_id = str(body.get("requirement_id") or "")
    if not requirement_id:
        raise HTTPException(status_code=400, detail="requirement_id required")
    row = repo.get_requirement(requirement_id)
    if not row:
        raise HTTPException(status_code=404, detail="requirement not found")

    req = AgentRequirement.from_db_row(row)
    seeder = _seeder(request)
    engine = _engine(request)
    facts = _facts(request, repo)
    seeded = seeder.seed(req, facts)
    score = engine.score(seeded.profile, seeded.usage, req, facts)
    alternatives = engine.alternatives(seeded, req, facts)

    session_id = f"ms-{uuid.uuid4().hex[:12]}"
    import json

    repo.upsert_modeler_session(
        id=session_id,
        requirement_id=requirement_id,
        profile_json=json.dumps(_profile_to_dict(seeded.profile), default=str),
        usage_json=json.dumps(seeded.usage.__dict__, default=str),
        last_score_json=json.dumps(score.inputs | {"total": score.total}, default=str),
    )

    return {
        "session_id": session_id,
        "requirement_id": requirement_id,
        "rationale_id": seeded.rationale_id,
        "rationale": seeded.rationale,
        "notes": seeded.notes,
        "available_channels": seeded.available_channels,
        "axes": {
            k: {
                "value": (v.value.value if hasattr(v.value, "value") else v.value),
                "locked": v.locked,
                "source": v.source,
                "rationale_id": v.rationale_id,
            }
            for k, v in seeded.axes.items()
        },
        "profile": _profile_to_dict(seeded.profile),
        "score": {
            "fit": score.fit,
            "cost_efficiency": score.cost_efficiency,
            "risk": score.risk,
            "compliance": score.compliance,
            "total": score.total,
            "monthly_usd": str(score.monthly_usd),
            "rationale": score.rationale,
            "inputs": score.inputs,
        },
        "alternatives": [
            {
                "agent_type": c.profile.agent_type.value,
                "channel": c.profile.channel.value,
                "score": {
                    "fit": c.score.fit,
                    "cost_efficiency": c.score.cost_efficiency,
                    "risk": c.score.risk,
                    "compliance": c.score.compliance,
                    "total": c.score.total,
                    "monthly_usd": str(c.score.monthly_usd),
                },
            }
            for c in alternatives[:10]
        ],
    }


@router.post("/modeler/refine")
def modeler_refine(
    request: Request,
    body: dict[str, Any] = Body(...),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    """Apply user edits to the seeded design and re-score."""
    import json

    from ..modeler import AgentRequirement

    session_id = str(body.get("session_id") or "")
    edits = body.get("edits") or {}
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    sess = repo.get_modeler_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")
    req_row = repo.get_requirement(sess["requirement_id"])
    if not req_row:
        raise HTTPException(status_code=404, detail="requirement not found")
    req = AgentRequirement.from_db_row(req_row)

    profile_data = json.loads(sess.get("profile_json") or "{}")
    usage_data = json.loads(sess.get("usage_json") or "{}")
    # Apply edits
    for k, v in edits.items():
        if k in profile_data:
            profile_data[k] = v
        elif k in usage_data:
            usage_data[k] = v
    # Coerce enum-typed fields
    if "agent_type" in profile_data and isinstance(profile_data["agent_type"], str):
        profile_data["agent_type"] = AgentType(profile_data["agent_type"])
    if "channel" in profile_data and isinstance(profile_data["channel"], str):
        profile_data["channel"] = Channel(profile_data["channel"])
    profile_data.pop("created_date", None)

    profile = AgentProfile(**{k: v for k, v in profile_data.items() if hasattr(AgentProfile, k) or k in AgentProfile.__dataclass_fields__})
    usage = InteractionProfile(**{k: v for k, v in usage_data.items() if k in InteractionProfile.__dataclass_fields__})

    engine = _engine(request)
    facts = _facts(request, repo)
    score = engine.score(profile, usage, req, facts)
    breakdown = request.app.state.cost_calculator.estimate(profile, usage)

    repo.upsert_modeler_session(
        id=session_id,
        requirement_id=sess["requirement_id"],
        profile_json=json.dumps(_profile_to_dict(profile), default=str),
        usage_json=json.dumps(usage.__dict__, default=str),
        last_score_json=json.dumps(score.inputs | {"total": score.total}, default=str),
    )
    return {
        "session_id": session_id,
        "profile": _profile_to_dict(profile),
        "score": {
            "fit": score.fit,
            "cost_efficiency": score.cost_efficiency,
            "risk": score.risk,
            "compliance": score.compliance,
            "total": score.total,
            "monthly_usd": str(score.monthly_usd),
            "rationale": score.rationale,
        },
        "breakdown": _breakdown_to_out(breakdown).model_dump(),
    }


@router.post("/modeler/promote")
def modeler_promote(
    request: Request,
    body: dict[str, Any] = Body(...),
    repo: Repository = Depends(_repo),
) -> dict[str, Any]:
    """Convert a finalised modeller session into a real AgentRow."""
    import json
    import uuid

    session_id = str(body.get("session_id") or "")
    agent_name = str(body.get("agent_name") or "").strip()
    owner = str(body.get("owner") or "").strip()
    cost_center = str(body.get("cost_center") or "").strip()
    if not session_id or not agent_name:
        raise HTTPException(
            status_code=400, detail="session_id and agent_name required"
        )
    sess = repo.get_modeler_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    profile_data = json.loads(sess.get("profile_json") or "{}")
    agent_id = profile_data.get("agent_id") or f"agt-{uuid.uuid4().hex[:10]}"

    repo.upsert_agent(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_type=str(profile_data.get("agent_type") or "declarative_public"),
        channel=str(profile_data.get("channel") or "m365_copilot"),
        owner=owner,
        cost_center=cost_center,
        environment=str(profile_data.get("environment") or "prod"),
        agent_365_registered=False,
        licensed_user_count=int(profile_data.get("licensed_user_count") or 0),
        unlicensed_user_count=int(profile_data.get("unlicensed_user_count") or 0),
        external_user_count=int(profile_data.get("external_user_count") or 0),
        avg_interactions_per_user_per_month=int(
            profile_data.get("avg_interactions_per_user_per_month") or 0
        ),
        # Mark provenance for downstream auditing.
        # The Agent table's source_system column is unused today, so we instead
        # emit a synthetic IngestionRun audit record.
    )
    repo.record_ingestion_run(
        job="modeler_promote",
        sdk_call="POST /api/v1/modeler/promote",
        rows_in=1,
        rows_written=1,
        status="ok",
    )
    repo.upsert_modeler_session(
        id=session_id,
        requirement_id=sess["requirement_id"],
        promoted_agent_id=agent_id,
    )
    return {"agent_id": agent_id, "session_id": session_id, "status": "promoted"}
