"""Pydantic schema definitions for the HTTP API.

Mirrors the dataclasses in ``ai_finops.domain.models`` but as Pydantic
models so FastAPI can validate / serialise them. Currency values are
serialised as strings to preserve Decimal precision.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import (
    AgentType,
    Channel,
    OptimisationCategory,
)


def _decimal_to_str(v: Decimal | str | int | float) -> str:
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


class AgentProfileIn(BaseModel):
    """Input shape for an agent in the what-if modeller."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str = ""
    agent_name: str = ""
    agent_type: AgentType = AgentType.DECLARATIVE_INSTRUCTION
    channel: Channel = Channel.M365_COPILOT
    build_platform: str = "agents_toolkit"
    owner: str = ""
    cost_center: str = ""
    environment: str = "prod"
    is_frontier_preview: bool = False

    uses_tenant_graph: bool = False
    uses_public_web: bool = False
    uses_dataverse: bool = False
    uses_ai_search: bool = False
    ai_search_tier: str | None = None
    ai_search_units: int = 0

    primary_model_id: str | None = None
    reasoning_model: bool = False
    uses_batch_api: bool = False
    prompt_caching_enabled: bool = False
    fine_tuned_model_id: str | None = None

    hosted_vcpu: float = 0.0
    hosted_memory_gib: float = 0.0
    hosted_hours_per_month: int = 0

    web_search_transactions: int = 0
    custom_search_transactions: int = 0
    code_interpreter_sessions: int = 0
    file_search_storage_gb: float = 0.0

    avg_credits_per_interaction: float | None = None
    avg_tokens_input_per_interaction: int | None = None
    avg_tokens_output_per_interaction: int | None = None
    avg_interactions_per_user_per_month: int | None = None
    cache_hit_rate: float = 0.0

    licensed_user_count: int = 0
    unlicensed_user_count: int = 0
    external_user_count: int = 0
    active_users_7d: int | None = None

    agent_365_registered: bool = False
    agent_365_owner_upn: str | None = None


class InteractionProfileIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    classic_answers_per_interaction: float = 0.0
    generative_answers_per_interaction: float = 1.0
    agent_actions_per_interaction: float = 0.0
    tenant_graph_grounding_per_interaction: float = 0.0
    agent_flow_actions_per_interaction: float = 0.0
    ai_tool_basic_responses_per_interaction: float = 0.0
    ai_tool_standard_responses_per_interaction: float = 0.0
    ai_tool_premium_responses_per_interaction: float = 0.0
    content_pages_per_interaction: float = 0.0


class EstimateRequest(BaseModel):
    profile: AgentProfileIn
    usage: InteractionProfileIn = Field(default_factory=InteractionProfileIn)
    period_months: int = 1
    scenario_name: str | None = None


class CompareRequest(BaseModel):
    base_profile: AgentProfileIn
    usage: InteractionProfileIn = Field(default_factory=InteractionProfileIn)
    agent_types: list[AgentType] | None = None
    period_months: int = 1


class OptimisationOut(BaseModel):
    category: OptimisationCategory
    title: str
    description: str
    monthly_saving_usd: str
    implementation_effort: str
    confidence: float
    before_cost_usd: str
    after_cost_usd: str
    evidence: str
    action_url: str | None = None
    agent_id: str | None = None


class CostBreakdownOut(BaseModel):
    scenario_name: str
    period_months: int
    utilisation_band: str
    confidence: str

    license_cost_total_usd: str
    license_detail: list[dict[str, Any]] = []

    credits_charged: int
    credits_zero_rated: int
    credits_shadow: int
    credits_cost_payg_usd: str
    credits_cost_pack_usd: str
    credits_packs_required: int
    credits_recommendation: str
    credits_detail: dict[str, int] = {}
    b2e_zero_rated: bool

    tokens_monthly: int
    azure_openai_cost_usd: str
    foundry_tools_cost_usd: str
    ai_search_cost_usd: str
    hosted_agent_compute_usd: str
    azure_total_usd: str

    total_monthly_usd: str
    total_annual_usd: str
    cost_per_interaction_usd: str
    cost_per_active_user_monthly_usd: str
    low_estimate_usd: str
    high_estimate_usd: str

    potential_savings_usd: str
    optimisation_recommendations: list[OptimisationOut] = []
    notes: list[str] = []


class CompareResponse(BaseModel):
    cheapest: CostBreakdownOut | None
    recommendation: str
    results: list[CostBreakdownOut]


class HealthResponse(BaseModel):
    status: str
    env: str
    rate_cards: list[dict[str, Any]]
