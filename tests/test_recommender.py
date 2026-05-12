"""Tests for the optimisation recommender."""
from __future__ import annotations

from decimal import Decimal

from ai_finops.domain.enums import AgentType, Channel, OptimisationCategory
from ai_finops.domain.models import AgentProfile, InteractionProfile
from ai_finops.optimisation.recommender import OptimisationRecommender
from ai_finops.services.cost_calculator import CostCalculator
from ai_finops.services.rate_card_service import RateCardService


def test_pack_vs_payg_recommendation(calculator: CostCalculator, rate_card_service: RateCardService):
    profile = AgentProfile(
        agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
        channel=Channel.TEAMS_STANDALONE,
        unlicensed_user_count=1,
        avg_interactions_per_user_per_month=30000,
    )
    usage = InteractionProfile(
        generative_answers_per_interaction=0,
        classic_answers_per_interaction=1,  # 1 credit per interaction
    )
    breakdown = calculator.estimate(profile, usage, period_months=1)
    rec = OptimisationRecommender(rate_card_service)
    recs = rec.recommend(profile, breakdown)
    cats = {r.category for r in recs}
    assert OptimisationCategory.PACK_VS_PAYG in cats


def test_prompt_caching_recommendation(calculator: CostCalculator, rate_card_service: RateCardService):
    profile = AgentProfile(
        agent_type=AgentType.FOUNDRY_NATIVE,
        channel=Channel.WEB_CHAT,
        unlicensed_user_count=100,
        avg_interactions_per_user_per_month=100,
        primary_model_id="gpt_5_4_mini",
        avg_tokens_input_per_interaction=2000,
        avg_tokens_output_per_interaction=200,
        prompt_caching_enabled=False,
    )
    breakdown = calculator.estimate(profile, InteractionProfile(), period_months=1)
    rec = OptimisationRecommender(rate_card_service)
    recs = rec.recommend(profile, breakdown)
    cats = {r.category for r in recs}
    assert OptimisationCategory.PROMPT_CACHING in cats
    assert all(r.monthly_saving_usd > Decimal("0") for r in recs)


def test_agent_technology_switch_recommendation(calculator: CostCalculator, rate_card_service: RateCardService):
    profile = AgentProfile(
        agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
        channel=Channel.WEB_CHAT,
        unlicensed_user_count=10,
        avg_interactions_per_user_per_month=100,
        uses_tenant_graph=False,
        uses_ai_search=False,
    )
    breakdown = calculator.estimate(
        profile, InteractionProfile(generative_answers_per_interaction=1), period_months=1
    )
    rec = OptimisationRecommender(rate_card_service)
    recs = rec.recommend(profile, breakdown)
    cats = {r.category for r in recs}
    assert OptimisationCategory.AGENT_TECHNOLOGY_SWITCH in cats
