"""Seed the AI FinOps database with demo data.

Usage::

    python -m ai_finops.seed [--reset]

Builds nine fictional agents covering all major AgentType variants,
generates six months of synthetic cost events using the production
``CostCalculator``, runs the OptimisationRecommender + AnomalyDetector
and persists everything via the Repository.
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .config import get_settings
from .db import (
    Repository,
    get_session_factory,
    init_db,
)
from .domain.enums import AgentType, Channel, Meter, UserLicenseType
from .domain.models import AgentProfile, CostBreakdown, InteractionProfile
from .governance import AnomalyDetector
from .optimisation.recommender import OptimisationRecommender
from .services.cost_calculator import CostCalculator
from .services.rate_card_service import RateCardService

logger = logging.getLogger("ai_finops.seed")

RNG = random.Random(7)


def _agent_profiles() -> list[AgentProfile]:
    """Hand-curated 9 agents covering all AgentType variants."""
    def base_owner(name: str) -> str:
        return f"{name}@fabrikam.com"
    return [
        AgentProfile(
            agent_id="agt-hr-policy",
            agent_name="HR Policy Buddy",
            agent_type=AgentType.DECLARATIVE_INSTRUCTION,
            channel=Channel.M365_COPILOT,
            owner=base_owner("hr.helpdesk"),
            cost_center="HR-001",
            uses_tenant_graph=True,
            licensed_user_count=4500,
            unlicensed_user_count=200,
            avg_interactions_per_user_per_month=8,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-sales-research",
            agent_name="Sales Research Assistant",
            agent_type=AgentType.DECLARATIVE_TENANT,
            channel=Channel.M365_COPILOT,
            owner=base_owner("sales.ops"),
            cost_center="SALES-100",
            uses_tenant_graph=True,
            uses_public_web=True,
            licensed_user_count=900,
            unlicensed_user_count=120,
            avg_interactions_per_user_per_month=20,
            web_search_transactions=12000,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-finance-close",
            agent_name="Finance Close Helper",
            agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
            channel=Channel.M365_COPILOT,
            owner=base_owner("finance.systems"),
            cost_center="FIN-200",
            uses_tenant_graph=True,
            uses_dataverse=True,
            licensed_user_count=300,
            unlicensed_user_count=40,
            avg_interactions_per_user_per_month=35,
            avg_credits_per_interaction=12.0,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-it-helpdesk",
            agent_name="IT Helpdesk Triage",
            agent_type=AgentType.COPILOT_STUDIO_DECLARATIVE,
            channel=Channel.TEAMS_COPILOT_EXTENSION,
            owner=base_owner("it.copilot"),
            cost_center="IT-300",
            uses_tenant_graph=True,
            licensed_user_count=6000,
            unlicensed_user_count=0,
            avg_interactions_per_user_per_month=5,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-marketing-brief",
            agent_name="Marketing Brief Author",
            agent_type=AgentType.HYBRID_STUDIO_FOUNDRY,
            channel=Channel.WEB_CHAT,
            owner=base_owner("marketing.ops"),
            cost_center="MKT-400",
            primary_model_id="gpt-4o-mini",
            uses_batch_api=True,
            prompt_caching_enabled=True,
            licensed_user_count=120,
            unlicensed_user_count=20,
            avg_interactions_per_user_per_month=18,
            avg_tokens_input_per_interaction=2500,
            avg_tokens_output_per_interaction=1200,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-product-faq",
            agent_name="Product FAQ Public",
            agent_type=AgentType.FOUNDRY_NATIVE,
            channel=Channel.CUSTOM_CHANNEL,
            owner=base_owner("product.web"),
            cost_center="PROD-500",
            primary_model_id="gpt-4o",
            uses_ai_search=True,
            ai_search_tier="standard",
            ai_search_units=2,
            external_user_count=1200,
            avg_tokens_input_per_interaction=1800,
            avg_tokens_output_per_interaction=900,
            avg_interactions_per_user_per_month=4,
        ),
        AgentProfile(
            agent_id="agt-legal-redline",
            agent_name="Legal Redline Reviewer",
            agent_type=AgentType.FOUNDRY_HOSTED,
            channel=Channel.WEB_CHAT,
            owner=base_owner("legal.tech"),
            cost_center="LEGAL-600",
            primary_model_id="gpt-4o",
            reasoning_model=True,
            fine_tuned_model_id="legal-redline-ft-v2",
            hosted_vcpu=2.0,
            hosted_memory_gib=8.0,
            hosted_hours_per_month=720,
            licensed_user_count=80,
            avg_tokens_input_per_interaction=8000,
            avg_tokens_output_per_interaction=2500,
            avg_interactions_per_user_per_month=15,
            agent_365_registered=False,
            is_frontier_preview=True,
        ),
        AgentProfile(
            agent_id="agt-eng-code-review",
            agent_name="Engineering Code Reviewer",
            agent_type=AgentType.HYBRID_STUDIO_FOUNDRY,
            channel=Channel.M365_COPILOT,
            owner=base_owner("eng.tools"),
            cost_center="ENG-700",
            primary_model_id="gpt-4o-mini",
            prompt_caching_enabled=True,
            licensed_user_count=2000,
            avg_interactions_per_user_per_month=22,
            avg_tokens_input_per_interaction=3500,
            avg_tokens_output_per_interaction=900,
            agent_365_registered=True,
        ),
        AgentProfile(
            agent_id="agt-supply-chain",
            agent_name="Supply-Chain Sentinel",
            agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
            channel=Channel.TEAMS_STANDALONE,
            owner=base_owner("supplychain.ops"),
            cost_center="SC-800",
            uses_dataverse=True,
            licensed_user_count=200,
            unlicensed_user_count=80,
            avg_interactions_per_user_per_month=12,
            avg_credits_per_interaction=15.0,
            agent_365_registered=False,
        ),
    ]


def _profile_to_agent_row(p: AgentProfile) -> dict:
    fields = {f: getattr(p, f) for f in p.__dataclass_fields__ if f != "created_date"}
    fields["agent_type"] = p.agent_type.value
    fields["channel"] = p.channel.value
    return fields


def _user_license_for(profile: AgentProfile) -> str:
    if profile.channel == Channel.M365_COPILOT:
        return UserLicenseType.M365_COPILOT_LICENSED.value
    return UserLicenseType.INTERNAL_UNLICENSED.value


def _emit_cost_events(
    profile: AgentProfile,
    breakdown: CostBreakdown,
    month_start: datetime,
    scale: Decimal,
) -> list[dict]:
    """Translate a CostBreakdown into one CostEventRow per non-zero meter."""
    events: list[dict] = []
    license_type = _user_license_for(profile)
    common = {
        "agent_id": profile.agent_id,
        "agent_name": profile.agent_name,
        "agent_type": profile.agent_type.value,
        "channel": profile.channel.value,
        "user_license_type": license_type,
        "cost_center": profile.cost_center,
        "owner": profile.owner,
        "environment": profile.environment,
    }
    license_cost = (breakdown.license_cost_total_usd * scale).quantize(Decimal("0.01"))
    if license_cost > 0:
        events.append(
            {
                **common,
                "id": f"ce-{uuid.uuid4().hex[:16]}",
                "timestamp": month_start + timedelta(days=1, hours=3),
                "meter": Meter.PER_SEAT.value,
                "sku_id": "M365_COPILOT",
                "assigned_users": int(profile.licensed_user_count or 0),
                "active_users_7d": int(
                    (profile.licensed_user_count or 0) * (0.6 + RNG.random() * 0.3)
                ),
                "cost_actual_usd": license_cost,
                "source_system": "seed",
            }
        )

    credits_charged = int(breakdown.credits_charged * float(scale))
    credits_zero = int(breakdown.credits_zero_rated * float(scale))
    credits_cost = (
        (breakdown.credits_cost_payg_usd + breakdown.credits_cost_pack_usd) * scale
    ).quantize(Decimal("0.000001"))
    if credits_charged > 0 or credits_zero > 0:
        events.append(
            {
                **common,
                "id": f"ce-{uuid.uuid4().hex[:16]}",
                "timestamp": month_start + timedelta(days=2, hours=6),
                "meter": Meter.COPILOT_CREDITS.value,
                "credits_consumed": credits_charged,
                "credits_shadow": credits_zero,
                "b2e_zero_rated": breakdown.b2e_zero_rated and credits_charged == 0,
                "cost_actual_usd": credits_cost,
                "source_system": "seed",
            }
        )

    azure_cost = (breakdown.azure_total_usd * scale).quantize(Decimal("0.000001"))
    if azure_cost > 0:
        tokens = int(breakdown.tokens_monthly * float(scale))
        events.append(
            {
                **common,
                "id": f"ce-{uuid.uuid4().hex[:16]}",
                "timestamp": month_start + timedelta(days=3, hours=9),
                "meter": Meter.AZURE_CONSUMPTION.value,
                "tokens_input": int(tokens * 0.6),
                "tokens_output": int(tokens * 0.4),
                "model_id": profile.primary_model_id,
                "azure_service": "azure_openai",
                "cost_actual_usd": azure_cost,
                "source_system": "seed",
            }
        )
    return events


def _spike_for_marketing(events: list[dict], agent_id: str) -> None:
    """Inject a token spike for the marketing agent (drives anomaly detector)."""
    spike_ts = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    events.append(
        {
            "id": f"ce-spike-{uuid.uuid4().hex[:8]}",
            "timestamp": spike_ts,
            "meter": Meter.AZURE_CONSUMPTION.value,
            "agent_id": agent_id,
            "agent_name": "Marketing Brief Author",
            "agent_type": AgentType.HYBRID_STUDIO_FOUNDRY.value,
            "channel": Channel.WEB_CHAT.value,
            "user_license_type": UserLicenseType.INTERNAL_UNLICENSED.value,
            "cost_center": "MKT-400",
            "owner": "marketing.ops@fabrikam.com",
            "environment": "prod",
            "tokens_input": 8_000_000,
            "tokens_output": 4_000_000,
            "model_id": "gpt-4o-mini",
            "azure_service": "azure_openai",
            "cost_actual_usd": Decimal("400.00"),
            "source_system": "seed",
        }
    )


def _seed(repo: Repository, rates: RateCardService) -> None:
    print("Seeding agents…", flush=True)
    profiles = _agent_profiles()
    for p in profiles:
        repo.upsert_agent(**_profile_to_agent_row(p))

    print("Seeding 6 months of cost events…", flush=True)
    calculator = CostCalculator(rates)
    recommender = OptimisationRecommender(rates)
    now = datetime.now(UTC).replace(tzinfo=None)
    all_events: list[dict] = []
    for p in profiles:
        breakdown = calculator.estimate(p, InteractionProfile())
        for m_back in range(6):
            year = now.year
            month = now.month - m_back
            while month <= 0:
                month += 12
                year -= 1
            month_start = datetime(year, month, 1)
            scale = Decimal(str(1 - m_back * 0.06))
            jitter = Decimal(str(0.95 + RNG.random() * 0.1))
            all_events.extend(_emit_cost_events(p, breakdown, month_start, scale * jitter))
    _spike_for_marketing(all_events, "agt-marketing-brief")
    repo.insert_cost_events(all_events)

    print("Seeding budgets…", flush=True)
    repo.create_budget(
        name="Tenant AI Budget", amount_usd=Decimal("250000"), period="monthly", scope="",
        alert_threshold_pct=85, owner="finops@fabrikam.com",
    )
    repo.create_budget(
        name="Sales Cost Center", amount_usd=Decimal("40000"), period="monthly",
        scope="cost_center:SALES-100", alert_threshold_pct=80, owner="sales.ops@fabrikam.com",
    )
    repo.create_budget(
        name="Finance Cost Center", amount_usd=Decimal("25000"), period="monthly",
        scope="cost_center:FIN-200", alert_threshold_pct=80, owner="finance.systems@fabrikam.com",
    )
    repo.create_budget(
        name="Production Environment", amount_usd=Decimal("180000"), period="monthly",
        scope="env:prod", alert_threshold_pct=90, owner="finops@fabrikam.com",
    )

    print("Seeding untagged spend rows…", flush=True)
    repo.insert_untagged_rows(
        [
            {
                "id": "unt-0001",
                "detected_at": now,
                "service_name": "Azure OpenAI",
                "resource_id": "/sub/abc/rg/orphan/openai-orphan-1",
                "resource_name": "openai-orphan-1",
                "cost_usd": Decimal("214.55"),
                "missing_tags": "AgentId,Owner",
            },
            {
                "id": "unt-0002",
                "detected_at": now,
                "service_name": "Azure AI Search",
                "resource_id": "/sub/abc/rg/orphan/search-orphan-1",
                "resource_name": "search-orphan-1",
                "cost_usd": Decimal("87.20"),
                "missing_tags": "AgentId,CostCenter,Owner,Environment",
            },
        ]
    )

    print("Generating optimisation recommendations…", flush=True)
    for p in profiles:
        breakdown = calculator.estimate(p, InteractionProfile())
        recs = recommender.recommend(p, breakdown)
        if recs:
            repo.replace_recommendations(
                p.agent_id,
                [
                    {
                        "category": r.category.value,
                        "title": r.title,
                        "description": r.description,
                        "monthly_saving_usd": r.monthly_saving_usd,
                        "implementation_effort": r.implementation_effort,
                        "confidence": float(r.confidence),
                        "before_cost_usd": r.before_cost_usd,
                        "after_cost_usd": r.after_cost_usd,
                        "evidence": r.evidence,
                        "action_url": r.action_url,
                    }
                    for r in recs
                ],
            )

    print("Running anomaly detector…", flush=True)
    detector = AnomalyDetector(repo, rates)
    anomalies = detector.detect()
    repo.replace_anomalies(anomalies)
    print(f"Seeded {len(profiles)} agents, {len(all_events)} cost events, "
          f"{len(anomalies)} anomalies.", flush=True)


def _reset_sqlite(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw = url[len("sqlite:///"):]
    if not raw or raw == ":memory:":
        return
    path = Path(raw).expanduser()
    if path.exists():
        path.unlink()
        print(f"Removed {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the AI FinOps database.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete the SQLite DB before seeding."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    if args.reset:
        _reset_sqlite(settings.database_url)

    init_db(settings.database_url)
    repo = Repository(get_session_factory(settings.database_url))
    rates = RateCardService(
        rate_card_dir=settings.rate_card_dir, stale_days=settings.rate_card_stale_days
    )
    if not args.reset:
        repo.truncate_all()
    _seed(repo, rates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
