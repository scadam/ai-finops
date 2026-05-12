"""CostCalculator — core three-meter cost engine.

Implements the algorithm in copilot-instructions.md §6.3:

1. For each user population segment (licensed, unlicensed, external):
   a. Determine ``is_zero_rated`` (B2E rule).
   b. Determine ``is_free_tier`` (declarative free tier).
   c. Per interaction event type, compute credits per interaction.
2. Sum monthly credits → choose pack vs PAYG (>=25k credits → pack).
3. Foundry token math (input + output, cached at 10%, batch 50%).
4. Hybrid Studio+Foundry: BOTH meters fire — sum, never choose one.
5. Per utilisation band: 75% / 100% / 125%.
6. Unit economics: cost/interaction, cost/active user.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from ..domain.enums import (
    B2E_ELIGIBLE_AGENT_TYPES,
    B2E_ELIGIBLE_CHANNELS,
    DECLARATIVE_FREE_TIER_AGENT_TYPES,
    AgentType,
    UserLicenseType,
)
from ..domain.models import (
    AgentProfile,
    CostBreakdown,
    InteractionProfile,
)
from .rate_card_service import RateCardService


def _d(value: Any) -> Decimal:
    """Coerce to Decimal via str (avoids float artefacts)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class CostCalculator:
    """Compute :class:`CostBreakdown` from an :class:`AgentProfile`.

    All rate values come from :class:`RateCardService`. Never hardcode prices.
    """

    def __init__(self, rate_card_service: RateCardService) -> None:
        self._rates = rate_card_service

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def estimate(
        self,
        profile: AgentProfile,
        usage: InteractionProfile | None = None,
        period_months: int = 1,
        scenario_name: str | None = None,
    ) -> CostBreakdown:
        """Compute the canonical cost breakdown for one agent profile."""
        usage = usage or InteractionProfile()
        breakdown = CostBreakdown(
            scenario_name=scenario_name or profile.agent_name or profile.agent_type.value,
            agent_profile=profile,
            period_months=period_months,
        )
        self._compute_credits(profile, usage, breakdown)
        self._compute_azure(profile, breakdown)
        self._compute_licenses(profile, breakdown, period_months)
        self._compute_totals(profile, usage, breakdown, period_months)
        self._compute_confidence(profile, breakdown)
        return breakdown

    def calculate_credits_per_interaction(self, usage: InteractionProfile) -> dict[str, float]:
        """Return per-event credit consumption for a single interaction.

        Used directly by tests (regression fixtures from spec §10.1).
        """
        rates = self._rates.cards.copilot_credits.get("consumption_rates", {})

        def rate(name: str) -> float:
            entry = rates.get(name) or {}
            return float(entry.get("credits", 0))

        # Per-response and per-event rates
        classic = usage.classic_answers_per_interaction * rate("classic_answer")
        generative = usage.generative_answers_per_interaction * rate("generative_answer")
        agent_action = usage.agent_actions_per_interaction * rate("agent_action")
        grounding = usage.tenant_graph_grounding_per_interaction * rate("tenant_graph_grounding")
        flow = (usage.agent_flow_actions_per_interaction / 100.0) * rate("agent_flow_actions")
        ai_basic = (usage.ai_tool_basic_responses_per_interaction / 10.0) * rate("ai_tools_basic")
        ai_std = (usage.ai_tool_standard_responses_per_interaction / 10.0) * rate("ai_tools_standard")
        ai_prem = (usage.ai_tool_premium_responses_per_interaction / 10.0) * rate("ai_tools_premium")
        content = usage.content_pages_per_interaction * rate("content_processing")

        per_event = {
            "classic": classic,
            "generative": generative,
            "agent_action": agent_action,
            "tenant_graph_grounding": grounding,
            "agent_flow_actions": flow,
            "ai_tools_basic": ai_basic,
            "ai_tools_standard": ai_std,
            "ai_tools_premium": ai_prem,
            "content_processing": content,
        }
        per_event["total"] = sum(per_event.values())
        return per_event

    # ------------------------------------------------------------------
    # B2E / free-tier rules
    # ------------------------------------------------------------------
    def is_b2e_zero_rated_for_segment(
        self,
        profile: AgentProfile,
        segment_license: UserLicenseType,
    ) -> bool:
        """Apply the B2E zero-rating rule. See copilot-instructions.md §2."""
        return (
            segment_license in {UserLicenseType.M365_COPILOT_LICENSED, UserLicenseType.M365_COPILOT_E7}
            and profile.channel in B2E_ELIGIBLE_CHANNELS
            and profile.agent_type in B2E_ELIGIBLE_AGENT_TYPES
        )

    def is_declarative_free_tier(self, profile: AgentProfile) -> bool:
        """Instruction-only / public-web-only declarative agents = $0 for all."""
        if profile.agent_type not in DECLARATIVE_FREE_TIER_AGENT_TYPES:
            return False
        # Free tier requires no tenant-data grounding
        return not profile.uses_tenant_graph and not profile.uses_dataverse

    # ------------------------------------------------------------------
    # Meter 2 — Copilot Credits
    # ------------------------------------------------------------------
    def _compute_credits(
        self,
        profile: AgentProfile,
        usage: InteractionProfile,
        breakdown: CostBreakdown,
    ) -> None:
        # Foundry-only agents do NOT fire credits.
        if profile.agent_type in {AgentType.FOUNDRY_NATIVE, AgentType.FOUNDRY_HOSTED}:
            return

        per_int = self.calculate_credits_per_interaction(usage)
        credits_per_interaction = per_int["total"]
        breakdown.credits_detail = {k: int(v) for k, v in per_int.items() if k != "total"}

        is_free_tier = self.is_declarative_free_tier(profile)
        interactions_per_user = profile.avg_interactions_per_user_per_month or 0

        # --- Licensed users (B2E zero-rating may apply) ---
        is_b2e_lic = self.is_b2e_zero_rated_for_segment(profile, UserLicenseType.M365_COPILOT_LICENSED)
        lic_total_credits = int(round(profile.licensed_user_count * interactions_per_user * credits_per_interaction))
        breakdown.credits_licensed_users = lic_total_credits

        # --- Unlicensed (internal) users ---
        unlic_total_credits = int(round(
            profile.unlicensed_user_count * interactions_per_user * credits_per_interaction
        ))
        breakdown.credits_unlicensed_users = unlic_total_credits

        # --- External users (always metered) ---
        ext_total_credits = int(round(
            profile.external_user_count * interactions_per_user * credits_per_interaction
        ))
        breakdown.credits_external_users = ext_total_credits

        zero_rated = 0
        charged = 0
        shadow = 0

        # Licensed segment
        if is_free_tier:
            zero_rated += lic_total_credits
        elif is_b2e_lic:
            zero_rated += lic_total_credits
            shadow += lic_total_credits
        else:
            charged += lic_total_credits

        # Unlicensed segment — free tier only
        if is_free_tier:
            zero_rated += unlic_total_credits
        else:
            charged += unlic_total_credits

        # External segment — never zero-rated except free tier
        if is_free_tier:
            zero_rated += ext_total_credits
        else:
            charged += ext_total_credits

        breakdown.credits_zero_rated = zero_rated
        breakdown.credits_charged = charged
        breakdown.credits_shadow = shadow
        breakdown.b2e_zero_rated = is_b2e_lic and profile.licensed_user_count > 0

        # --- Pack vs PAYG ---
        pricing = self._rates.cards.copilot_credits.get("pricing", {})
        payg_per_credit = _d(pricing.get("payg_per_credit_usd", 0))
        pack = pricing.get("prepaid_pack", {})
        pack_credits = int(pack.get("credits", 25000) or 25000)
        pack_price = _d(pack.get("price_usd", 200))
        threshold = int(self._rates.cards.copilot_credits
                        .get("pack_strategy", {})
                        .get("recommendation_threshold_credits_per_month", pack_credits))

        breakdown.credits_cost_payg_usd = (payg_per_credit * Decimal(charged)).quantize(Decimal("0.0001"))

        if charged >= threshold:
            # Use floor(packs) and let PAYG cover the overflow — per spec:
            # "Always stack PAYG as overflow when pack is active to prevent agent shutdown".
            packs = max(1, charged // pack_credits)
            full_pack_credits = packs * pack_credits
            overflow = max(0, charged - full_pack_credits)
            pack_total = pack_price * Decimal(packs) + payg_per_credit * Decimal(overflow)
            # If for some reason ceil(packs) is cheaper (when overflow PAYG cost > one pack),
            # take the cheaper option.
            ceil_packs = packs + (1 if overflow > 0 else 0)
            ceil_total = pack_price * Decimal(ceil_packs)
            chosen_packs, chosen_total = (
                (packs, pack_total) if pack_total <= ceil_total else (ceil_packs, ceil_total)
            )
            breakdown.credits_packs_required = int(chosen_packs)
            breakdown.credits_cost_pack_usd = chosen_total.quantize(Decimal("0.0001"))
            breakdown.credits_recommendation = (
                "pack" if breakdown.credits_cost_pack_usd <= breakdown.credits_cost_payg_usd else "payg"
            )
        else:
            breakdown.credits_cost_pack_usd = breakdown.credits_cost_payg_usd
            breakdown.credits_recommendation = "payg"

    # ------------------------------------------------------------------
    # Meter 3 — Azure consumption
    # ------------------------------------------------------------------
    def _compute_azure(self, profile: AgentProfile, breakdown: CostBreakdown) -> None:
        # Studio-only agents (no Foundry) skip Azure tokens.
        studio_only_types = {
            AgentType.DECLARATIVE_INSTRUCTION,
            AgentType.DECLARATIVE_PUBLIC,
            AgentType.DECLARATIVE_TENANT,
            AgentType.COPILOT_STUDIO_CUSTOM,
            AgentType.COPILOT_STUDIO_DECLARATIVE,
        }
        is_studio_only = profile.agent_type in studio_only_types

        # --- Azure OpenAI tokens (Foundry / hybrid) ---
        if not is_studio_only and profile.primary_model_id:
            self._compute_openai_tokens(profile, breakdown)

        # --- Foundry hosted-agent compute ---
        if profile.agent_type == AgentType.FOUNDRY_HOSTED and profile.hosted_hours_per_month > 0:
            f = self._rates.cards.foundry_agent_service.get("hosted_agents", {})
            vcpu_rate = _d(f.get("vcpu_per_hour", 0))
            mem_rate = _d(f.get("memory_gib_per_hour", 0))
            hours = Decimal(profile.hosted_hours_per_month)
            breakdown.hosted_agent_compute_usd = (
                vcpu_rate * Decimal(str(profile.hosted_vcpu)) * hours
                + mem_rate * Decimal(str(profile.hosted_memory_gib)) * hours
            ).quantize(Decimal("0.0001"))

        # --- Foundry tools ---
        tools = self._rates.cards.foundry_agent_service.get("tools", {})
        ws_rate = _d(tools.get("web_search_per_1k_transactions", 0))
        cs_rate = _d(tools.get("custom_search_per_1k_transactions", 0))
        ci_rate = _d(tools.get("code_interpreter_per_session", 0))
        fs_rate = _d(tools.get("file_search_storage_per_gb_day", 0))
        fs_free = _d(tools.get("file_search_free_gb", 0))

        tools_cost = Decimal("0")
        if profile.web_search_transactions:
            tools_cost += ws_rate * Decimal(profile.web_search_transactions) / Decimal("1000")
        if profile.custom_search_transactions:
            tools_cost += cs_rate * Decimal(profile.custom_search_transactions) / Decimal("1000")
        if profile.code_interpreter_sessions:
            tools_cost += ci_rate * Decimal(profile.code_interpreter_sessions)
        if profile.file_search_storage_gb:
            billable_gb = max(Decimal("0"), Decimal(str(profile.file_search_storage_gb)) - fs_free)
            tools_cost += fs_rate * billable_gb * Decimal("30")  # ~monthly
        breakdown.foundry_tools_cost_usd = tools_cost.quantize(Decimal("0.0001"))

        # --- AI Search ---
        if profile.uses_ai_search and profile.ai_search_tier:
            tiers = self._rates.cards.ai_search.get("tiers", {})
            tier = tiers.get(profile.ai_search_tier, {})
            per_su = _d(tier.get("monthly_per_su", 0))
            units = max(1, profile.ai_search_units or 1)
            breakdown.ai_search_cost_usd = (per_su * Decimal(units)).quantize(Decimal("0.0001"))

        breakdown.azure_total_usd = (
            breakdown.azure_openai_cost_usd
            + breakdown.foundry_tools_cost_usd
            + breakdown.ai_search_cost_usd
            + breakdown.hosted_agent_compute_usd
            + breakdown.infrastructure_cost_usd
        ).quantize(Decimal("0.0001"))

    def _compute_openai_tokens(self, profile: AgentProfile, breakdown: CostBreakdown) -> None:
        models = self._rates.cards.azure_openai.get("models", {})
        model = models.get(profile.primary_model_id)
        if not model:
            breakdown.notes.append(
                f"Unknown model_id '{profile.primary_model_id}' — Azure OpenAI cost not computed."
            )
            return

        total_users = profile.licensed_user_count + profile.unlicensed_user_count + profile.external_user_count
        interactions = total_users * (profile.avg_interactions_per_user_per_month or 0)
        in_per = profile.avg_tokens_input_per_interaction or 0
        out_per = profile.avg_tokens_output_per_interaction or 0

        tokens_input = interactions * in_per
        tokens_output = interactions * out_per
        breakdown.tokens_monthly = tokens_input + tokens_output

        input_rate = _d(model.get("input_per_1m", 0))
        output_rate = _d(model.get("output_per_1m", 0))
        cached_rate = _d(model.get("cached_input_per_1m", input_rate * Decimal("0.10")))

        cache_hit = max(0.0, min(1.0, profile.cache_hit_rate))
        cached_tokens = int(tokens_input * cache_hit) if profile.prompt_caching_enabled else 0
        non_cached_tokens = tokens_input - cached_tokens

        token_cost = (
            (Decimal(non_cached_tokens) * input_rate / Decimal("1000000"))
            + (Decimal(tokens_output) * output_rate / Decimal("1000000"))
            + (Decimal(cached_tokens) * cached_rate / Decimal("1000000"))
        )

        if profile.uses_batch_api:
            batch_disc = _d(model.get("batch_discount", 0.5))
            token_cost = token_cost * batch_disc

        breakdown.azure_openai_cost_usd = token_cost.quantize(Decimal("0.0001"))

    # ------------------------------------------------------------------
    # Meter 1 — Per-seat licenses
    # ------------------------------------------------------------------
    def _compute_licenses(
        self,
        profile: AgentProfile,
        breakdown: CostBreakdown,
        period_months: int,
    ) -> None:
        # Licenses are only attributable to an agent if explicitly reported here;
        # in this engine we attribute the per-licensed-user M365 Copilot add-on cost
        # only when the agent uses the M365 channel (otherwise the seat is not
        # required for this agent specifically and would be double-counted).
        if profile.channel not in B2E_ELIGIBLE_CHANNELS:
            return
        if profile.licensed_user_count <= 0:
            return
        skus = self._rates.cards.per_seat.get("skus", {})
        sku = skus.get("m365_copilot_addon", {})
        rate = _d(sku.get("price_usd", 0))
        per_user = rate
        total = (rate * Decimal(profile.licensed_user_count)).quantize(Decimal("0.0001"))
        breakdown.license_cost_per_user_usd = per_user
        breakdown.license_cost_total_usd = total
        breakdown.license_detail = [
            {
                "sku": "m365_copilot_addon",
                "name": sku.get("name", "Microsoft 365 Copilot (add-on)"),
                "users": profile.licensed_user_count,
                "monthly_rate_usd": str(per_user),
                "total_usd": str(total),
            }
        ]

    # ------------------------------------------------------------------
    # Totals + sensitivity bands + unit economics
    # ------------------------------------------------------------------
    def _compute_totals(
        self,
        profile: AgentProfile,
        usage: InteractionProfile,
        breakdown: CostBreakdown,
        period_months: int,
    ) -> None:
        credits_cost = (
            breakdown.credits_cost_pack_usd
            if breakdown.credits_recommendation == "pack"
            else breakdown.credits_cost_payg_usd
        )
        monthly = (
            breakdown.license_cost_total_usd
            + credits_cost
            + breakdown.azure_total_usd
        ).quantize(Decimal("0.0001"))

        breakdown.total_monthly_usd = monthly
        breakdown.total_annual_usd = (monthly * Decimal(12)).quantize(Decimal("0.0001"))

        # Sensitivity (75% / 125%) — applied to consumption-based meters only;
        # license cost is fixed.
        variable = monthly - breakdown.license_cost_total_usd
        breakdown.low_estimate_usd = (
            breakdown.license_cost_total_usd + variable * Decimal("0.75")
        ).quantize(Decimal("0.0001"))
        breakdown.high_estimate_usd = (
            breakdown.license_cost_total_usd + variable * Decimal("1.25")
        ).quantize(Decimal("0.0001"))

        total_users = (
            profile.licensed_user_count + profile.unlicensed_user_count + profile.external_user_count
        )
        interactions_total = total_users * (profile.avg_interactions_per_user_per_month or 0)
        if interactions_total > 0:
            breakdown.cost_per_interaction_usd = (
                monthly / Decimal(interactions_total)
            ).quantize(Decimal("0.000001"))
        active = profile.active_users_7d if profile.active_users_7d is not None else total_users
        if active > 0:
            breakdown.cost_per_active_user_monthly_usd = (
                monthly / Decimal(active)
            ).quantize(Decimal("0.0001"))

    def _compute_confidence(self, profile: AgentProfile, breakdown: CostBreakdown) -> None:
        if profile.is_frontier_preview:
            breakdown.confidence = "low"
            breakdown.notes.append("Frontier preview pricing — flagged as MODERATE/LOW confidence.")
        elif profile.primary_model_id in {"gpt_5_4_pro"}:
            breakdown.confidence = "medium"
        else:
            breakdown.confidence = "high"

    # ------------------------------------------------------------------
    # Helpers used by the modeller for what-if comparisons
    # ------------------------------------------------------------------
    def estimate_with_overrides(
        self,
        profile: AgentProfile,
        usage: InteractionProfile,
        period_months: int = 1,
        scenario_name: str | None = None,
        **overrides: Any,
    ) -> CostBreakdown:
        """Apply attribute overrides to ``profile`` then estimate. Pure function."""
        new_profile = replace(profile, **overrides)
        return self.estimate(new_profile, usage, period_months=period_months, scenario_name=scenario_name)
