"""Domain dataclasses for the canonical cost ledger and what-if modeller.

See copilot-instructions.md §5.2 — §5.4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .enums import (
    AgentType,
    Channel,
    Meter,
    OptimisationCategory,
    UserLicenseType,
)


@dataclass
class CostEvent:
    """One row in the canonical cost ledger.

    Sourced from either M365 Credits API, Graph license API, or Azure Cost
    Management FOCUS exports. All monetary values use ``Decimal``.
    """

    id: str
    timestamp: datetime
    meter: Meter
    agent_id: str
    agent_name: str
    agent_type: AgentType
    channel: Channel
    user_license_type: UserLicenseType

    # Cost attribution
    cost_center: str = ""
    owner: str = ""
    environment: str = "prod"
    application: str = ""

    # Copilot Credits meter fields
    credits_consumed: int | None = None
    credits_shadow: int | None = None
    b2e_zero_rated: bool = False

    # Azure consumption meter fields
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_cached: int | None = None
    model_id: str | None = None
    azure_service: str | None = None
    azure_resource_id: str | None = None

    # Per-seat meter fields
    sku_id: str | None = None
    assigned_users: int | None = None
    active_users_7d: int | None = None

    # Computed costs
    cost_actual_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_shadow_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    discount_applied_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    # Source metadata
    source_system: str = ""
    focus_billing_period: str | None = None
    raw_record_id: str | None = None

    def to_focus_row(self) -> dict[str, Any]:
        """Emit this event in FOCUS 1.1 format for interoperability."""
        return {
            "BillingPeriodStart": self.focus_billing_period,
            "ChargePeriodStart": self.timestamp.isoformat(),
            "BilledCost": str(self.cost_actual_usd),
            "EffectiveCost": str(self.cost_actual_usd - self.discount_applied_usd),
            "ServiceName": self.azure_service or self.meter.value,
            "ServiceCategory": "AI and Machine Learning",
            "ResourceId": self.azure_resource_id or "",
            "ResourceName": self.agent_name,
            "ResourceType": self.agent_type.value,
            "Tags": {
                "AgentId": self.agent_id,
                "CostCenter": self.cost_center,
                "Owner": self.owner,
                "Environment": self.environment,
                "Application": self.application,
            },
            "UsageQuantity": self.credits_consumed
            if self.meter == Meter.COPILOT_CREDITS
            else (self.tokens_input or 0) + (self.tokens_output or 0),
            "UsageUnit": "credits"
            if self.meter == Meter.COPILOT_CREDITS
            else "tokens"
            if self.meter == Meter.AZURE_CONSUMPTION
            else "seats",
        }


@dataclass
class AgentProfile:
    """Technical configuration of an agent. Used by the What-If modeller."""

    agent_id: str = ""
    agent_name: str = ""
    agent_type: AgentType = AgentType.DECLARATIVE_INSTRUCTION
    channel: Channel = Channel.M365_COPILOT
    build_platform: str = "agents_toolkit"
    owner: str = ""
    cost_center: str = ""
    environment: str = "prod"
    created_date: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "production"
    is_frontier_preview: bool = False

    # Grounding configuration
    uses_tenant_graph: bool = False
    uses_public_web: bool = False
    uses_dataverse: bool = False
    uses_ai_search: bool = False
    ai_search_tier: str | None = None
    ai_search_units: int = 0

    # Model configuration (for Foundry/Azure OpenAI)
    primary_model_id: str | None = None
    reasoning_model: bool = False
    uses_batch_api: bool = False
    prompt_caching_enabled: bool = False
    fine_tuned_model_id: str | None = None

    # Hosted-agent compute (Foundry hosted)
    hosted_vcpu: float = 0.0
    hosted_memory_gib: float = 0.0
    hosted_hours_per_month: int = 0

    # Foundry tools (per month)
    web_search_transactions: int = 0
    custom_search_transactions: int = 0
    code_interpreter_sessions: int = 0
    file_search_storage_gb: float = 0.0

    # Consumption profile (avg per interaction)
    avg_credits_per_interaction: float | None = None
    avg_tokens_input_per_interaction: int | None = None
    avg_tokens_output_per_interaction: int | None = None
    avg_interactions_per_user_per_month: int | None = None
    cache_hit_rate: float = 0.0  # 0.0-1.0

    # User population
    licensed_user_count: int = 0
    unlicensed_user_count: int = 0
    external_user_count: int = 0
    active_users_7d: int | None = None

    # Agent 365 governance
    agent_365_registered: bool = False
    agent_365_owner_upn: str | None = None


@dataclass
class InteractionProfile:
    """Per-interaction breakdown of credit-consuming events.

    Mirrors the consumption_rates section of copilot_credits.yaml. Each
    field is the *count of events* per single user interaction.
    """

    classic_answers_per_interaction: float = 0.0
    generative_answers_per_interaction: float = 1.0
    agent_actions_per_interaction: float = 0.0
    tenant_graph_grounding_per_interaction: float = 0.0
    agent_flow_actions_per_interaction: float = 0.0           # individual actions (will be /100)
    ai_tool_basic_responses_per_interaction: float = 0.0      # individual responses (will be /10)
    ai_tool_standard_responses_per_interaction: float = 0.0
    ai_tool_premium_responses_per_interaction: float = 0.0
    content_pages_per_interaction: float = 0.0


@dataclass
class OptimisationRecommendation:
    """A single, ranked savings opportunity."""

    category: OptimisationCategory
    title: str
    description: str
    monthly_saving_usd: Decimal
    implementation_effort: str            # "low", "medium", "high"
    confidence: float                     # 0.0-1.0
    before_cost_usd: Decimal
    after_cost_usd: Decimal
    evidence: str
    action_url: str | None = None
    agent_id: str | None = None


@dataclass
class CostBreakdown:
    """Output of the What-If cost estimator for one agent/scenario."""

    scenario_name: str
    agent_profile: AgentProfile
    period_months: int = 1
    utilisation_band: str = "expected_100pct"

    # Meter 1 — Per-seat
    license_cost_total_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    license_cost_per_user_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    license_detail: list[dict[str, Any]] = field(default_factory=list)

    # Meter 2 — Copilot Credits
    credits_licensed_users: int = 0
    credits_unlicensed_users: int = 0
    credits_external_users: int = 0
    credits_zero_rated: int = 0
    credits_charged: int = 0
    credits_shadow: int = 0
    credits_cost_payg_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    credits_cost_pack_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    credits_packs_required: int = 0
    credits_recommendation: str = "payg"     # payg | pack | cccu
    credits_detail: dict[str, int] = field(default_factory=dict)
    b2e_zero_rated: bool = False

    # Meter 3 — Azure consumption
    tokens_monthly: int = 0
    azure_openai_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    foundry_tools_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    ai_search_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    hosted_agent_compute_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    infrastructure_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    azure_total_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    # Totals
    total_monthly_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    total_annual_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_per_interaction_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_per_active_user_monthly_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    # Sensitivity bands (from utilisation 75% / 100% / 125%)
    low_estimate_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    high_estimate_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    confidence: str = "high"                 # high | medium | low

    # Optimisation candidates
    potential_savings_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    optimisation_recommendations: list[OptimisationRecommendation] = field(default_factory=list)

    notes: list[str] = field(default_factory=list)
