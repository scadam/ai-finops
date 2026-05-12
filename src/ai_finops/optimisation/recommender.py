"""OptimisationRecommender — maps the 11 rules from copilot-instructions.md §6.4
into ranked :class:`OptimisationRecommendation` objects.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from ..domain.enums import (
    B2E_ELIGIBLE_CHANNELS,
    AgentType,
    OptimisationCategory,
)
from ..domain.models import (
    AgentProfile,
    CostBreakdown,
    OptimisationRecommendation,
)
from ..services.rate_card_service import RateCardService


def _d(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


class OptimisationRecommender:
    """Generate ranked recommendations against an agent's CostBreakdown."""

    def __init__(self, rate_card_service: RateCardService) -> None:
        self._rates = rate_card_service

    def recommend(
        self,
        profile: AgentProfile,
        breakdown: CostBreakdown,
    ) -> list[OptimisationRecommendation]:
        recs: list[OptimisationRecommendation] = []
        for rule in self._rules():
            rec = rule(profile, breakdown)
            if rec is not None and rec.monthly_saving_usd > Decimal("0"):
                recs.append(rec)
        recs.sort(key=lambda r: r.monthly_saving_usd, reverse=True)
        return recs

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _rules(self) -> list[Callable[[AgentProfile, CostBreakdown], OptimisationRecommendation | None]]:
        return [
            self._rule_license_channel_routing,
            self._rule_model_downshift,
            self._rule_prompt_caching,
            self._rule_batch_api,
            self._rule_ptu_reservation,
            self._rule_graph_grounding_toggle,
            self._rule_classic_answer_fallback,
            self._rule_zombie_ft_model,
            self._rule_pack_vs_payg,
            self._rule_license_right_sizing,
            self._rule_agent_technology_switch,
        ]

    # --- Rule 1: license_channel_routing ---
    def _rule_license_channel_routing(self, p: AgentProfile, c: CostBreakdown):
        if p.licensed_user_count <= 0:
            return None
        if p.channel in B2E_ELIGIBLE_CHANNELS:
            return None
        if c.credits_charged <= 0:
            return None
        # Saving = credits attributable to licensed users that would zero-rate
        total_users = p.licensed_user_count + p.unlicensed_user_count + p.external_user_count
        if total_users == 0:
            return None
        share = Decimal(p.licensed_user_count) / Decimal(total_users)
        payg_rate = _d(self._rates.cards.copilot_credits.get("pricing", {}).get("payg_per_credit_usd", 0))
        saving = (Decimal(c.credits_charged) * share * payg_rate).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.LICENSE_CHANNEL_ROUTING,
            title="Move licensed users to M365 channel for zero-rated credits",
            description=(
                "Licensed users currently access this agent on a non-M365 channel and "
                "are paying credits that would otherwise be zero-rated under the B2E rule."
            ),
            monthly_saving_usd=saving,
            implementation_effort="medium",
            confidence=0.8,
            before_cost_usd=c.total_monthly_usd,
            after_cost_usd=c.total_monthly_usd - saving,
            evidence="B2E zero-rating rule — copilot-instructions.md §2",
            agent_id=p.agent_id or None,
        )

    # --- Rule 2: model_downshift ---
    def _rule_model_downshift(self, p: AgentProfile, c: CostBreakdown):
        if p.primary_model_id not in {"gpt_4o", "gpt_5_4", "gpt_4_1"}:
            return None
        if c.azure_openai_cost_usd <= Decimal("0"):
            return None
        models = self._rates.cards.azure_openai.get("models", {})
        big = models.get(p.primary_model_id, {})
        mini = models.get("gpt_4o_mini", {})
        if not big or not mini:
            return None
        big_in = _d(big.get("input_per_1m", 0))
        mini_in = _d(mini.get("input_per_1m", 0))
        if big_in <= 0:
            return None
        # Assume 60% of queries can be routed to mini
        ratio = Decimal("1") - (mini_in / big_in)
        saving = (Decimal("0.60") * c.azure_openai_cost_usd * ratio).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.MODEL_DOWNSHIFT,
            title="Route simple queries to GPT-4o mini",
            description="Up to ~16× cheaper input than full GPT-4o; route simple intents to mini.",
            monthly_saving_usd=saving,
            implementation_effort="medium",
            confidence=0.7,
            before_cost_usd=c.azure_openai_cost_usd,
            after_cost_usd=c.azure_openai_cost_usd - saving,
            evidence="azure.microsoft.com/pricing/details/azure-openai",
            agent_id=p.agent_id or None,
        )

    # --- Rule 3: prompt_caching ---
    def _rule_prompt_caching(self, p: AgentProfile, c: CostBreakdown):
        if p.prompt_caching_enabled:
            return None
        if p.primary_model_id not in {
            "gpt_5_4", "gpt_5_4_long", "gpt_5_4_mini", "gpt_5_4_nano", "gpt_4_1", "gpt_4_1_mini",
        }:
            return None
        if c.azure_openai_cost_usd <= Decimal("0"):
            return None
        # System prompts ~40% of input; cached at 10% of full price
        saving = (Decimal("0.40") * c.azure_openai_cost_usd * Decimal("0.90")).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.PROMPT_CACHING,
            title="Enable prompt caching",
            description="Cached input is billed at ~10% of full input rate. Recommended for repeated system prompts.",
            monthly_saving_usd=saving,
            implementation_effort="low",
            confidence=0.85,
            before_cost_usd=c.azure_openai_cost_usd,
            after_cost_usd=c.azure_openai_cost_usd - saving,
            evidence="azure_openai.yaml prompt_caching.discount_multiplier",
            agent_id=p.agent_id or None,
        )

    # --- Rule 4: batch_api ---
    def _rule_batch_api(self, p: AgentProfile, c: CostBreakdown):
        if p.uses_batch_api:
            return None
        if p.agent_type not in {AgentType.FOUNDRY_NATIVE, AgentType.FOUNDRY_HOSTED}:
            return None
        if c.azure_openai_cost_usd <= Decimal("0"):
            return None
        saving = (c.azure_openai_cost_usd * Decimal("0.50")).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.BATCH_API,
            title="Convert async workloads to Batch API (50% discount)",
            description="Eligible Foundry workloads (summarisation, classification, embeddings) save ~50%.",
            monthly_saving_usd=saving,
            implementation_effort="medium",
            confidence=0.6,
            before_cost_usd=c.azure_openai_cost_usd,
            after_cost_usd=c.azure_openai_cost_usd - saving,
            evidence="Batch API 50% discount — Global Standard only",
            agent_id=p.agent_id or None,
        )

    # --- Rule 5: ptu_reservation ---
    def _rule_ptu_reservation(self, p: AgentProfile, c: CostBreakdown):
        if not p.primary_model_id:
            return None
        if c.tokens_monthly < 2_000_000_000:
            return None
        saving = (c.azure_openai_cost_usd * Decimal("0.40")).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.PTU_RESERVATION,
            title="Commit to Provisioned Throughput Units (PTU)",
            description="At >=2B tokens/month a 1-year PTU reservation typically saves 30-50%.",
            monthly_saving_usd=saving,
            implementation_effort="high",
            confidence=0.65,
            before_cost_usd=c.azure_openai_cost_usd,
            after_cost_usd=c.azure_openai_cost_usd - saving,
            evidence="azure_openai.yaml ptu.reservation_discounts",
            agent_id=p.agent_id or None,
        )

    # --- Rule 6: graph_grounding_toggle ---
    def _rule_graph_grounding_toggle(self, p: AgentProfile, c: CostBreakdown):
        if not p.uses_tenant_graph:
            return None
        grounding_credits = c.credits_detail.get("tenant_graph_grounding", 0)
        if grounding_credits <= 500:
            return None
        payg_rate = _d(self._rates.cards.copilot_credits.get("pricing", {}).get("payg_per_credit_usd", 0))
        saving = (Decimal(grounding_credits) * payg_rate).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.GRAPH_GROUNDING_TOGGLE,
            title="Disable tenant Graph grounding when public web suffices",
            description="Tenant Graph grounding is 10 credits per event; public web grounding is free.",
            monthly_saving_usd=saving,
            implementation_effort="low",
            confidence=0.5,
            before_cost_usd=c.total_monthly_usd,
            after_cost_usd=c.total_monthly_usd - saving,
            evidence="copilot_credits.yaml consumption_rates.tenant_graph_grounding",
            agent_id=p.agent_id or None,
        )

    # --- Rule 7: classic_answer_fallback ---
    def _rule_classic_answer_fallback(self, p: AgentProfile, c: CostBreakdown):
        gen_credits = c.credits_detail.get("generative", 0)
        if gen_credits <= 5000:
            return None
        payg_rate = _d(self._rates.cards.copilot_credits.get("pricing", {}).get("payg_per_credit_usd", 0))
        saving = (Decimal(gen_credits) * Decimal("0.50") * payg_rate).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.CLASSIC_ANSWER_FALLBACK,
            title="Use classic answers for FAQ topics",
            description="Classic = 1 credit, Generative = 2 credits. Route FAQ topics to classic.",
            monthly_saving_usd=saving,
            implementation_effort="low",
            confidence=0.6,
            before_cost_usd=c.total_monthly_usd,
            after_cost_usd=c.total_monthly_usd - saving,
            evidence="copilot_credits.yaml consumption_rates.classic_answer vs generative_answer",
            agent_id=p.agent_id or None,
        )

    # --- Rule 8: zombie_ft_model ---
    def _rule_zombie_ft_model(self, p: AgentProfile, c: CostBreakdown):
        if not p.fine_tuned_model_id:
            return None
        ft = self._rates.cards.azure_infrastructure.get("fine_tuned_models", {})
        floor = _d(ft.get("deployed_idle_monthly_low", 1836))
        return OptimisationRecommendation(
            category=OptimisationCategory.ZOMBIE_FT_MODEL,
            title="Decommission idle fine-tuned model",
            description="Fine-tuned model deployments cost $1,836–$2,160/month regardless of usage.",
            monthly_saving_usd=floor,
            implementation_effort="low",
            confidence=0.7,
            before_cost_usd=c.total_monthly_usd,
            after_cost_usd=max(Decimal("0"), c.total_monthly_usd - floor),
            evidence="azure_infrastructure.yaml fine_tuned_models",
            agent_id=p.agent_id or None,
        )

    # --- Rule 9: pack_vs_payg ---
    def _rule_pack_vs_payg(self, p: AgentProfile, c: CostBreakdown):
        if c.credits_charged < 25000:
            return None
        saving = c.credits_cost_payg_usd - c.credits_cost_pack_usd
        if saving <= Decimal("0"):
            return None
        return OptimisationRecommendation(
            category=OptimisationCategory.PACK_VS_PAYG,
            title="Switch from PAYG to prepaid credit pack",
            description="Pack: $200/25k credits ($0.008/credit) vs PAYG $0.01/credit — 20% saving.",
            monthly_saving_usd=saving.quantize(Decimal("0.01")),
            implementation_effort="low",
            confidence=0.95,
            before_cost_usd=c.credits_cost_payg_usd,
            after_cost_usd=c.credits_cost_pack_usd,
            evidence="copilot_credits.yaml pricing.prepaid_pack",
            agent_id=p.agent_id or None,
        )

    # --- Rule 10: license_right_sizing ---
    def _rule_license_right_sizing(self, p: AgentProfile, c: CostBreakdown):
        if p.licensed_user_count <= 0 or p.active_users_7d is None:
            return None
        if p.active_users_7d / max(1, p.licensed_user_count) >= 0.5:
            return None
        unused = p.licensed_user_count - p.active_users_7d
        addon = self._rates.cards.per_seat.get("skus", {}).get("m365_copilot_addon", {})
        rate = _d(addon.get("price_usd", 30))
        saving = (Decimal(unused) * rate).quantize(Decimal("0.01"))
        return OptimisationRecommendation(
            category=OptimisationCategory.LICENSE_RIGHT_SIZING,
            title="Right-size M365 Copilot licenses",
            description=f"{unused} of {p.licensed_user_count} seats inactive in last 7 days.",
            monthly_saving_usd=saving,
            implementation_effort="high",
            confidence=0.5,
            before_cost_usd=c.license_cost_total_usd,
            after_cost_usd=c.license_cost_total_usd - saving,
            evidence="per_seat.yaml skus.m365_copilot_addon",
            agent_id=p.agent_id or None,
        )

    # --- Rule 11: agent_technology_switch ---
    def _rule_agent_technology_switch(self, p: AgentProfile, c: CostBreakdown):
        if p.agent_type not in {AgentType.COPILOT_STUDIO_CUSTOM, AgentType.DECLARATIVE_TENANT}:
            return None
        if p.uses_tenant_graph or p.uses_ai_search:
            return None
        if c.credits_cost_payg_usd <= Decimal("0"):
            return None
        return OptimisationRecommendation(
            category=OptimisationCategory.AGENT_TECHNOLOGY_SWITCH,
            title="Switch to instruction-only declarative agent (free for all users)",
            description="Without tenant grounding/AI Search this workload qualifies for the declarative free tier.",
            monthly_saving_usd=c.credits_cost_payg_usd.quantize(Decimal("0.01")),
            implementation_effort="medium",
            confidence=0.65,
            before_cost_usd=c.credits_cost_payg_usd,
            after_cost_usd=Decimal("0"),
            evidence="copilot_credits.yaml declarative_free_tier",
            agent_id=p.agent_id or None,
        )
