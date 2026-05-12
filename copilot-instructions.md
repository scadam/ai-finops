# AI FinOps — Microsoft AI Frontier Platform
## GitHub Copilot Instructions (Claude Opus 4.7)

> **Purpose:** These instructions define the full scope, architecture, data models, business logic, and implementation requirements for an enterprise AI FinOps application targeting the Microsoft AI Frontier Platform. Every cost calculation, technology decision, and UI element must be grounded in the rate cards and rules below. Do not hardcode any dollar amount — load all rates from `config/rate_cards/`.

---

## 1. Project Overview

Build a full-stack web application that enables enterprise tenants to:

1. **See** — unified cost ledger across all Microsoft AI meters (licenses, Copilot Credits, Azure consumption)
2. **Understand** — cost attribution by agent, team, cost centre, channel, user population
3. **Model** — what-if scenarios comparing agent technologies before committing to build
4. **Optimise** — ranked, actionable recommendations with before/after cost impact
5. **Govern** — budgets, alerts, anomaly detection, commitment planning, reporting

The application must be self-contained and deployable to Azure (App Service + Azure SQL + Azure Functions + Storage Account). It integrates with Microsoft Graph API (license data + Copilot Credits reports) and Azure Cost Management (Azure consumption in FOCUS format).

---

## 2. The Three-Meter Model (Core Domain Concept)

**Every Microsoft AI cost line belongs to exactly one primary meter. Never mix meters in one cost row.**

```
METER 1 — PER-SEAT LICENSE
  └── M365 Copilot, Agent 365, M365 E7, Copilot Studio (maker seat)
  └── Fixed monthly charge; not usage-dependent
  └── Source: Graph API license assignments

METER 2 — COPILOT CREDITS
  └── Copilot Studio custom agents, declarative agents with tenant-data grounding
  └── Credit-based consumption; 1 credit = $0.01 PAYG
  └── Source: M365 admin center Graph API (Credits Usage Report)
  └── KEY RULE: Zero-rated for M365 Copilot-licensed users in M365 channel (B2E)

METER 3 — AZURE CONSUMPTION
  └── Azure OpenAI tokens, Foundry Agent Service (compute + tools), AI Search, Storage,
       Functions, Logic Apps, Application Insights
  └── Pay-per-use; no seat dependency
  └── Source: Azure Cost Management FOCUS exports
```

**The B2E Zero-Rating Rule** (must be applied in every cost calculation):
```
is_zero_rated = (
    user.has_m365_copilot_license == True
    AND channel IN ["m365_copilot", "teams_copilot_extension"]
    AND agent_type IN ["declarative_tenant", "declarative_public", "declarative_instruction",
                       "copilot_studio_custom", "copilot_studio_declarative"]
    AND within_fair_use_limits == True
)
# If is_zero_rated: credit cost = $0, but ALWAYS record shadow credits for utilisation reporting
```

**The Declarative Free Tier** (no credits regardless of license):
```
is_free_tier = (
    agent_type IN ["declarative_instruction", "declarative_public"]
    # No tenant-data grounding; instructions + public web only
)
# If is_free_tier: credit cost = $0 for ALL users (licensed or not)
```

**Hybrid Foundry+Studio De-duplication Rule**:
```
# When a Copilot Studio agent calls a Foundry endpoint:
# - Copilot Credits meter fires for Studio orchestration
# - Azure OpenAI token meter fires for Foundry model inference
# BOTH meters apply — sum them; do NOT choose one
```

---

## 3. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend API | Python 3.11+, FastAPI, async SQLAlchemy | Async I/O for Graph + Azure Cost API calls |
| Background jobs | Azure Functions (Python) + Azure Service Bus | Scheduled FOCUS imports, credit report pulls |
| Database | Azure SQL (Hyperscale or Standard) | FOCUS exports are relational; time-series views on top |
| Cache | Azure Cache for Redis | Rate card hot-reload; B2E resolution cache |
| Frontend | TypeScript 5+, React 18, Vite, Tanstack Query | Modern SPA; Tanstack for async data |
| Charts | Recharts 2.x | MIT license; composable |
| Component library | shadcn/ui (Radix + Tailwind CSS) | Accessible; Microsoft Fabric-compatible palette |
| Auth | MSAL.js (frontend) + `msal` Python (backend) | Azure AD / Entra ID SSO |
| Infrastructure | Bicep (IaC) | Reproducible Azure deployments |
| Testing | pytest + pytest-asyncio (backend), Vitest + Testing Library (frontend) | |
| CI/CD | GitHub Actions | |

---

## 4. Rate Card Configuration (YAML — never hardcode in code)

All pricing lives under `config/rate_cards/`. Hot-reload from disk on app start and every 60 minutes. Flag `stale_since` when a rate card has not been refreshed from the Azure Retail Prices API within 7 days.

### `config/rate_cards/per_seat.yaml`
```yaml
# All prices USD per user per month, annual commitment, as of 2026-05-12
# Source: https://www.microsoft.com/en-us/microsoft-365-copilot/pricing
effective_date: "2026-05-12"
skus:
  m365_copilot_addon:
    name: "Microsoft 365 Copilot (add-on)"
    price_usd: 30.00
    billing_period: monthly
    annual_commit: true
    base_license_required: true          # requires E3/E5/Business Standard/Premium
    grants_b2e_zero_rating: true
    grants_studio_maker_rights: true

  agent_365:
    name: "Agent 365"
    price_usd: 15.00
    billing_period: monthly
    annual_commit: true
    ga_date: "2026-05-01"
    note: "Governance control plane only. Does NOT include agent build/run cost."
    grants_b2e_zero_rating: false

  m365_e7_frontier:
    name: "Microsoft 365 E7 Frontier Suite"
    price_usd: 99.00
    billing_period: monthly
    annual_commit: true
    ga_date: "2026-05-01"
    includes: ["e5_base", "m365_copilot_addon", "entra_suite", "agent_365"]
    grants_b2e_zero_rating: true
    grants_studio_maker_rights: true

  m365_copilot_chat:
    name: "Microsoft 365 Copilot Chat"
    price_usd: 0.00
    billing_period: monthly
    note: "Free with eligible M365 subscription. Unlicensed users hit Copilot Credits meter."
    grants_b2e_zero_rating: false

  m365_e3:
    name: "Microsoft 365 E3"
    price_usd: 36.00
    billing_period: monthly
    annual_commit: true
    note: "Rises to $39 on 2026-07-01 per Microsoft Dec 2025 announcement — single-source, flag as moderate confidence"
    price_usd_post_july_2026: 39.00   # forward-looking, moderate confidence

  m365_e5:
    name: "Microsoft 365 E5"
    price_usd: 57.00
    billing_period: monthly
    annual_commit: true
    price_usd_post_july_2026: 60.00   # forward-looking, moderate confidence

base_license_options:
  - m365_e3
  - m365_e5
  - m365_business_standard   # $12.50
  - m365_business_premium    # $22.00
```

### `config/rate_cards/copilot_credits.yaml`
```yaml
# Source: https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management
# Source: https://learn.microsoft.com/en-us/microsoft-copilot-studio/billing-licensing
effective_date: "2026-05-12"

pricing:
  payg_per_credit_usd: 0.01
  prepaid_pack:
    price_usd: 200.00
    credits: 25000
    per_credit_effective: 0.008
    billing: monthly_tenant_level
    rollover: false

  pre_purchase_plan_cccu:
    usd_per_cccu: 1.00
    credits_per_cccu: 100
    commitment: annual
    note: "Volume-tiered discounts available; contact Microsoft for tiers"

consumption_rates:
  # All rates in Copilot Credits per event
  # B2E zero-rating: ALL these = 0 when (user has M365 Copilot AND M365 channel)
  classic_answer:
    credits: 1
    description: "Static authored response from a topic"
    b2e_zero_rated: true

  generative_answer:
    credits: 2
    description: "LLM-generated response"
    b2e_zero_rated: true

  agent_action:
    credits: 5
    description: "Trigger, deep-reasoning, topic-transition, Computer-Use action"
    b2e_zero_rated: true
    note: "Stacks with base answer credits; does NOT replace them"

  tenant_graph_grounding:
    credits: 10
    description: "Per RAG event over tenant Graph (SharePoint, OneDrive, Graph connectors)"
    b2e_zero_rated: true
    unit: per_message

  agent_flow_actions:
    credits: 13
    description: "Per 100 Power Automate flow actions triggered by agent"
    b2e_zero_rated: true
    unit: per_100_actions

  ai_tools_basic:
    credits: 1
    description: "Lightweight prompt tools"
    b2e_zero_rated: true
    unit: per_10_responses

  ai_tools_standard:
    credits: 15
    description: "Standard model tools"
    b2e_zero_rated: true
    unit: per_10_responses

  ai_tools_premium:
    credits: 100
    description: "Reasoning-model surcharge — STACKS with base answer credits, does not replace"
    b2e_zero_rated: true
    unit: per_10_responses
    stacks_with: ["generative_answer", "agent_action"]

  content_processing:
    credits: 8
    description: "Document/image extraction per page"
    b2e_zero_rated: true
    unit: per_page

pack_strategy:
  recommendation_threshold_credits_per_month: 25000
  note: "Always stack PAYG as overflow when pack is active to prevent agent shutdown"

b2e_zero_rating:
  eligible_channels: ["m365_copilot", "teams_copilot_extension"]
  eligible_agent_types:
    - declarative_instruction
    - declarative_public
    - declarative_tenant
    - copilot_studio_custom
    - copilot_studio_declarative
  requires: "user.has_m365_copilot_license == true"
  note: "Shadow credits must still be recorded for utilisation reporting"

declarative_free_tier:
  # Instruction-only or public-web-only declarative agents cost $0 for ALL users
  eligible_agent_types:
    - declarative_instruction
    - declarative_public
  all_users_free: true
  trigger: "No tenant-data grounding (no SharePoint/OneDrive/Graph connectors)"
```

### `config/rate_cards/azure_openai.yaml`
```yaml
# Source: https://azure.microsoft.com/en-us/pricing/details/azure-openai/
# Source: https://deploybase.ai/articles/azure-openai-pricing
effective_date: "2026-05-12"
currency: USD
unit: per_1m_tokens

models:
  gpt_5_4:
    display_name: "GPT-5.4"
    context_window_k: 128
    input_per_1m: 2.50
    cached_input_per_1m: 0.25
    output_per_1m: 15.00
    batch_discount: 0.50

  gpt_5_4_long:
    display_name: "GPT-5.4 (>272k context)"
    context_window_k: 1024
    input_per_1m: 5.00
    cached_input_per_1m: 0.50
    output_per_1m: 22.50
    batch_discount: 0.50

  gpt_5_4_pro:
    display_name: "GPT-5.4 Pro"
    context_window_k: 272
    input_per_1m: 30.00
    output_per_1m: 180.00
    note: "Frontier model — verify GA pricing before building cost models"

  gpt_5_4_mini:
    display_name: "GPT-5.4 mini"
    input_per_1m: 0.75
    cached_input_per_1m: 0.08
    output_per_1m: 4.50
    batch_discount: 0.50

  gpt_5_4_nano:
    display_name: "GPT-5.4 nano"
    input_per_1m: 0.20
    cached_input_per_1m: 0.02
    output_per_1m: 1.25
    batch_discount: 0.50

  gpt_4o:
    display_name: "GPT-4o"
    input_per_1m: 2.50
    output_per_1m: 10.00
    batch_discount: 0.50
    ptu_per_hour: 40.00
    ptu_break_even_tokens_per_month: 2_000_000_000

  gpt_4o_mini:
    display_name: "GPT-4o mini"
    input_per_1m: 0.15
    output_per_1m: 0.60
    batch_discount: 0.50
    ptu_per_hour: 10.00

  gpt_4_1:
    display_name: "GPT-4.1"
    input_per_1m: 2.00
    output_per_1m: 8.00
    batch_discount: 0.50
    ptu_per_hour: 80.00

  gpt_4_1_mini:
    display_name: "GPT-4.1 mini"
    input_per_1m: 0.40
    output_per_1m: 1.60
    batch_discount: 0.50

  gpt_4_turbo:
    display_name: "GPT-4 Turbo"
    input_per_1m: 10.00
    output_per_1m: 30.00
    ptu_per_hour: 100.00

prompt_caching:
  discount_multiplier: 0.10    # cached input = 10% of full input price
  note: "Supported on GPT-5.4, GPT-5.4 mini/nano, GPT-4.1 family"

ptu:
  min_commitment_units: 100
  reservation_discounts:
    one_month: 0.30     # 30% off
    one_year: 0.50      # 50% off
  compute_hour_per_month: 730
```

### `config/rate_cards/foundry_agent_service.yaml`
```yaml
# Source: https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/
effective_date: "2026-05-12"

native_agents:
  runtime_cost: 0.00
  note: "No charge for creating or running Foundry-native agents; pay for tokens + tools only"

hosted_agents:
  vcpu_per_hour: 0.0994
  memory_gib_per_hour: 0.0118
  note: "Customer-dedicated containers; Microsoft Agent Framework, LangGraph etc."

tools:
  file_search_storage_per_gb_day: 0.11
  file_search_free_gb: 1
  code_interpreter_per_session: 0.033
  web_search_per_1k_transactions: 14.00
  custom_search_per_1k_transactions: 14.00

foundry_iq_connections:
  note: "Logic Apps connectors, Microsoft Fabric, SharePoint, Bing Grounding — billed separately per their own rate cards"
```

### `config/rate_cards/ai_search.yaml`
```yaml
# Source: https://azure.microsoft.com/en-us/pricing/details/search/
effective_date: "2026-05-12"

tiers:
  free:
    monthly_per_su: 0.00
    storage_gb: 0.05
    max_indexes: 3
  basic:
    monthly_per_su: 73.73
    storage_gb: 15
  s1:
    monthly_per_su: 245.28
    storage_gb: 160
  s2:
    monthly_per_su: 981.12
    storage_gb: 512
  s3:
    monthly_per_su: 1962.24
    storage_gb: 1024
  l1:
    monthly_per_su: 2802.47
    storage_gb: 2048
  l2:
    monthly_per_su: 5604.21
    storage_gb: 4096

addons:
  semantic_ranker_progressive: true   # progressive pricing; see Microsoft estimator
  agentic_retrieval_per_1m_tokens: 0.022
  agentic_retrieval_free_tokens: 50_000_000

note: "Always-on fixed monthly; scale tiers are 4x cost steps — use Microsoft capacity estimator before scaling"
```

### `config/rate_cards/azure_infrastructure.yaml`
```yaml
# Supporting services for AI agent workloads
effective_date: "2026-05-12"

azure_functions:
  consumption_per_1m_executions: 0.20
  memory_gb_s: 0.000016
  free_executions_per_month: 1_000_000

logic_apps:
  consumption_per_action: 0.000025
  note: "1400+ connectors; major hidden cost at scale — alert when monthly actions exceed 1M"

storage:
  hot_per_gb_month: 0.018
  cool_per_gb_month: 0.01
  archive_per_gb_month: 0.001
  lifecycle_policy_note: "Apply auto-tiering for conversation history older than 30 days"

application_insights:
  log_analytics_per_gb: 2.30
  note: "Add 5-10% to AI workload cost; tag all telemetry with AgentId"

fine_tuned_models:
  deployed_idle_monthly_low: 1836.00
  deployed_idle_monthly_high: 2160.00
  anomaly_threshold_days_idle: 7
  note: "ZOMBIE alert: fine-tuned model deployed >7 days with <1 invocation/day"
```

---

## 5. Domain Model

### 5.1 Core Enumerations

```python
# src/domain/enums.py
from enum import Enum

class Meter(str, Enum):
    PER_SEAT = "per_seat"
    COPILOT_CREDITS = "copilot_credits"
    AZURE_CONSUMPTION = "azure_consumption"

class AgentType(str, Enum):
    DECLARATIVE_INSTRUCTION = "declarative_instruction"   # Free for all users
    DECLARATIVE_PUBLIC = "declarative_public"             # Free for all users
    DECLARATIVE_TENANT = "declarative_tenant"             # Metered for unlicensed users
    COPILOT_STUDIO_CUSTOM = "copilot_studio_custom"       # Always metered, B2E zero-rated
    COPILOT_STUDIO_DECLARATIVE = "copilot_studio_declarative"  # Built in Studio, on M365 orch
    FOUNDRY_NATIVE = "foundry_native"                     # Azure consumption only
    FOUNDRY_HOSTED = "foundry_hosted"                     # Azure compute + tokens
    HYBRID_STUDIO_FOUNDRY = "hybrid_studio_foundry"       # Both meters fire

class Channel(str, Enum):
    M365_COPILOT = "m365_copilot"          # B2E zero-rating applies
    TEAMS_COPILOT_EXTENSION = "teams_copilot_extension"  # B2E zero-rating applies
    TEAMS_STANDALONE = "teams_standalone"  # No zero-rating
    WEB_CHAT = "web_chat"
    CUSTOM_CHANNEL = "custom_channel"
    COPILOT_CHAT_FREE = "copilot_chat_free"

class UserLicenseType(str, Enum):
    M365_COPILOT_LICENSED = "m365_copilot_licensed"       # Full B2E zero-rating
    M365_COPILOT_E7 = "m365_copilot_e7"                   # Same as above (E7 includes Copilot)
    INTERNAL_UNLICENSED = "internal_unlicensed"           # Has M365 but no Copilot add-on
    CONTRACTOR = "contractor"                              # External, metered
    EXTERNAL_CUSTOMER = "external_customer"               # B2C, always metered
    ANONYMOUS = "anonymous"                               # Public-facing, always metered

class OptimisationCategory(str, Enum):
    LICENSE_CHANNEL_ROUTING = "license_channel_routing"
    MODEL_DOWNSHIFT = "model_downshift"
    PROMPT_CACHING = "prompt_caching"
    BATCH_API = "batch_api"
    PTU_RESERVATION = "ptu_reservation"
    GRAPH_GROUNDING_TOGGLE = "graph_grounding_toggle"
    CLASSIC_ANSWER_FALLBACK = "classic_answer_fallback"
    ZOMBIE_FT_MODEL = "zombie_ft_model"
    IDLE_ENDPOINT = "idle_endpoint"
    AI_SEARCH_RIGHTSIZING = "ai_search_rightsizing"
    LICENSE_RIGHT_SIZING = "license_right_sizing"
    PACK_VS_PAYG = "pack_vs_payg"
    AGENT_TECHNOLOGY_SWITCH = "agent_technology_switch"
```

### 5.2 Cost Event (Canonical Ledger Row)

```python
# src/domain/models.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from .enums import Meter, AgentType, Channel, UserLicenseType

@dataclass
class CostEvent:
    """One row in the canonical cost ledger. Sourced from either M365 Credits API or Azure Cost Management FOCUS."""
    id: str                              # UUID
    timestamp: datetime                  # UTC
    meter: Meter
    agent_id: str
    agent_name: str
    agent_type: AgentType
    channel: Channel
    user_license_type: UserLicenseType

    # Cost attribution
    cost_center: str
    owner: str
    environment: str                     # prod / staging / dev
    application: str

    # Copilot Credits meter fields (Meter.COPILOT_CREDITS)
    credits_consumed: Optional[int] = None
    credits_shadow: Optional[int] = None  # Even when zero-rated, record shadow credits
    b2e_zero_rated: bool = False

    # Azure consumption meter fields (Meter.AZURE_CONSUMPTION)
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    tokens_cached: Optional[int] = None
    model_id: Optional[str] = None
    azure_service: Optional[str] = None   # e.g., "azure_openai", "ai_search", "functions"
    azure_resource_id: Optional[str] = None

    # Per-seat meter fields (Meter.PER_SEAT)
    sku_id: Optional[str] = None
    assigned_users: Optional[int] = None
    active_users_7d: Optional[int] = None  # For utilisation tracking

    # Computed costs (set by CostCalculator, never stored raw)
    cost_actual_usd: Decimal = field(default=Decimal("0"))
    cost_shadow_usd: Decimal = field(default=Decimal("0"))  # What it WOULD cost if not zero-rated
    discount_applied_usd: Decimal = field(default=Decimal("0"))

    # Source metadata
    source_system: str = ""   # "m365_credits_report", "azure_focus_export", "graph_license_api"
    focus_billing_period: Optional[str] = None
    raw_record_id: Optional[str] = None

    def to_focus_row(self) -> dict:
        """Emit this event in FOCUS 1.1 format for interoperability."""
        ...
```

### 5.3 Agent Profile

```python
@dataclass
class AgentProfile:
    """
    Describes an agent's technical configuration — used by the What-If modeler
    to compute expected costs before the agent is built.
    """
    agent_id: str
    agent_name: str
    agent_type: AgentType
    channel: Channel
    build_platform: str          # "agents_toolkit", "copilot_studio", "foundry_sdk", "agent_builder"
    owner: str
    cost_center: str
    environment: str
    created_date: datetime
    status: str                  # "production", "staging", "dev", "preview_frontier"
    is_frontier_preview: bool    # Frontier program features; pricing may change at GA

    # Grounding configuration
    uses_tenant_graph: bool      # SharePoint / OneDrive / Graph connectors
    uses_public_web: bool
    uses_dataverse: bool
    uses_ai_search: bool
    ai_search_tier: Optional[str] = None

    # Model configuration (for Foundry/Azure OpenAI)
    primary_model_id: Optional[str] = None
    reasoning_model: bool = False
    uses_batch_api: bool = False
    prompt_caching_enabled: bool = False
    fine_tuned_model_id: Optional[str] = None

    # Consumption profile (from observed data or estimates)
    avg_credits_per_interaction: Optional[float] = None
    avg_tokens_input_per_interaction: Optional[int] = None
    avg_tokens_output_per_interaction: Optional[int] = None
    avg_interactions_per_user_per_month: Optional[int] = None

    # User population (resolved from Graph API)
    licensed_user_count: int = 0
    unlicensed_user_count: int = 0
    external_user_count: int = 0

    # Agent 365 governance
    agent_365_registered: bool = False
    agent_365_owner_upn: Optional[str] = None
```

### 5.4 Cost Breakdown (What-If Output)

```python
@dataclass
class CostBreakdown:
    """Output of the What-If cost estimator for one agent/scenario."""
    scenario_name: str
    agent_profile: AgentProfile
    utilisation_band: str            # "low_75pct", "expected_100pct", "high_125pct"
    period_months: int

    # Meter 1 — Per-seat
    license_cost_total_usd: Decimal
    license_cost_per_user_usd: Decimal
    license_detail: list[dict]       # [{sku, users, monthly_rate, total}]

    # Meter 2 — Copilot Credits
    credits_licensed_users: int
    credits_unlicensed_users: int
    credits_external_users: int
    credits_zero_rated: int          # Shadow: what would have been charged
    credits_charged: int             # Actual billable credits
    credits_cost_payg_usd: Decimal
    credits_cost_pack_usd: Decimal   # If pack purchase is optimal
    credits_packs_required: int
    credits_recommendation: str      # "payg" | "pack" | "cccu"
    credits_detail: list[dict]

    # Meter 3 — Azure consumption
    tokens_monthly: int
    azure_openai_cost_usd: Decimal
    foundry_tools_cost_usd: Decimal
    ai_search_cost_usd: Decimal
    hosted_agent_compute_usd: Decimal
    infrastructure_cost_usd: Decimal  # Functions, Logic Apps, Storage, App Insights
    azure_total_usd: Decimal

    # Totals
    total_monthly_usd: Decimal
    total_annual_usd: Decimal
    cost_per_interaction_usd: Decimal
    cost_per_active_user_monthly_usd: Decimal

    # Savings opportunities
    potential_savings_usd: Decimal
    optimisation_recommendations: list["OptimisationRecommendation"]

    # Sensitivity
    low_estimate_usd: Decimal    # 75% utilisation
    high_estimate_usd: Decimal   # 125% utilisation
    confidence: str              # "high", "medium", "low" (low if preview pricing)

@dataclass
class OptimisationRecommendation:
    category: OptimisationCategory
    title: str
    description: str
    monthly_saving_usd: Decimal
    implementation_effort: str    # "low", "medium", "high"
    confidence: float             # 0.0-1.0
    before_cost_usd: Decimal
    after_cost_usd: Decimal
    action_url: Optional[str]    # Link to Microsoft docs or admin portal
    evidence: str                # Which rate card rules underpin this
```

---

## 6. Module Specifications

### 6.1 Module 1 — Ingestion

**Purpose:** Pull raw data from all Microsoft APIs and normalise into the canonical cost ledger.

**Triggers:** Azure Function timer — run every 4 hours for credits, daily at 02:00 UTC for FOCUS exports.

```python
# src/ingestion/graph_credits_puller.py
"""
Pull M365 Copilot Credits usage from Graph API.
Endpoint: GET /reports/getCopilotCreditsUsage
Requires: Reports.Read.All permission

Fields to extract per row:
  - userId, userPrincipalName
  - agentId, agentName
  - billingPolicyId
  - creditsUsed (total)
  - creditsBreakdown: {classic, generative, agentAction, tenantGraphGrounding,
                       agentFlowActions, aiToolsBasic, aiToolsStandard, aiToolsPremium,
                       contentProcessing}
  - isZeroRated (B2E flag from API)
  - reportDate

Notes:
- 30-day rolling window in current preview; store raw JSON before normalising
- Alert if a single user exceeds 2,000 credits in a day (M365 admin center threshold)
- Always request with $top=999 and paginate via @odata.nextLink
"""

# src/ingestion/focus_importer.py
"""
Import Azure Cost Management FOCUS-format exports from Azure Data Lake Storage.
Schedule: daily trigger on new blob in container 'focus-exports/{date}/'.

FOCUS 1.1 fields to map:
  BillingAccountId, BillingAccountName, BilledCost, EffectiveCost,
  ResourceId, ResourceName, ResourceType, ServiceName, ServiceCategory,
  SubAccountId, SubAccountName, Region, Tags, BillingPeriodStart,
  BillingPeriodEnd, UsageQuantity, UsageUnit, PricingUnit

AI service detection:
  ServiceName == "Azure OpenAI" → Meter.AZURE_CONSUMPTION, extract model from Tags.Model
  ServiceName == "Azure AI Search" → ai_search cost
  ServiceName contains "AI Foundry" → foundry cost
  ResourceType == "Microsoft.CognitiveServices/accounts" → OpenAI
  Tags.WorkloadType == "copilot-studio-agent" OR "declarative-agent" → override agent_type

Required tag validation:
  On import, check for: CostCenter, Owner, Environment, Application, WorkloadType, Model, AgentId
  Rows missing any tag → write to untagged_spend table + emit fix-it alert
"""

# src/ingestion/license_puller.py
"""
Pull Microsoft 365 license assignments for user population analysis.
Graph API: GET /users?$select=id,userPrincipalName,assignedLicenses,signInActivity
Requires: User.Read.All, AuditLog.Read.All permissions

For each user, determine UserLicenseType:
  - has SKU "Microsoft 365 Copilot" (GUID: 639dec6b-bb19-468b-871c-c5c441c4b0cb)?
    → UserLicenseType.M365_COPILOT_LICENSED
  - has M365 E7 SKU? → UserLicenseType.M365_COPILOT_E7
  - has M365 license but no Copilot? → UserLicenseType.INTERNAL_UNLICENSED
  - external user (#EXT#)? → UserLicenseType.CONTRACTOR

Cache results in Redis for 4 hours — license changes are infrequent.

Compute utilisation signal:
  - signInActivity.lastSignInDateTime within 7 days → active
  - Assign to agent's credited interactions via userId join in credits report
"""

# src/ingestion/agent_registry_puller.py
"""
Pull Agent 365 registry inventory (when tenant has Agent 365 licenses).
Graph API: GET /agentRegistry/agents  (preview endpoint — gracefully handle 404)
Returns: agentId, displayName, buildPlatform, status, ownerObjectId, createdDateTime

Also scan for agents via:
  - Copilot Studio: Power Platform Management API  GET /environments/{env}/bots
  - Azure AI Foundry: Azure Resource Manager  GET /providers/Microsoft.MachineLearningServices/workspaces/.../agents
  - Azure AI projects list for hosted-agent resource groups

Merge into AgentProfile objects. Flag agents NOT in Agent 365 registry that are in production.
"""
```

### 6.2 Module 2 — Allocation

**Purpose:** Attribute every cost line to a team/application/cost centre. Handle shared workloads.

```python
# src/allocation/tagger.py
"""
Tag inheritance rules (mirror Azure Cost Management behaviour):
  1. Resource-level tag wins over resource-group tag
  2. Missing tags → inherit from resource-group → subscription
  3. After inheritance, if still missing → write to fix_it_queue

Tag enrichment from Agent 365 registry:
  If cost row has AgentId tag → look up AgentProfile → inherit Owner, CostCenter, Application
"""

# src/allocation/split_cost.py
"""
Shared workload cost splitting.
When one Foundry deployment or AI Search instance serves multiple agents:
  
  Supported split keys:
    - proportional_invocations: split by invocation count (default)
    - proportional_tokens: split by token volume
    - equal: divide evenly
    - manual: fixed percentage weights per cost centre (configured in YAML)

Split rules config: config/allocation/split_rules.yaml
Each rule: {resource_id, split_key, allocations: [{cost_center, weight}]}
"""
```

### 6.3 Module 3 — What-If Cost Modeler (Core Feature)

This is the most important module. It answers: "If I build this agent this way, what will it cost?"

```python
# src/modeler/cost_calculator.py

class CostCalculator:
    """
    Given an AgentProfile and usage assumptions, compute CostBreakdown.
    Load all rates from RateCardService (hot-reloaded from YAML).
    
    Core algorithm:
    
    1. FOR EACH user population segment (licensed, unlicensed, external):
       a. Determine is_zero_rated (B2E rule)
       b. Determine is_free_tier (declarative free tier)
       c. For each interaction event type (classic, generative, grounding, action, etc.):
          credits = events_per_interaction[event_type] * consumption_rate[event_type]
          if is_zero_rated or is_free_tier:
              shadow_credits += credits
              billable_credits += 0
          else:
              billable_credits += credits
       d. Monthly credits for segment = users * interactions_per_user * billable_credits
    
    2. Total monthly billable credits → choose pack vs PAYG:
       if monthly_credits >= 25000:
           packs = ceil(monthly_credits / 25000)
           pack_cost = packs * 200
           overflow_credits = (monthly_credits % 25000) if PAYG overflow enabled else 0
       else:
           pack_cost = 0
           payg_cost = monthly_credits * 0.01
    
    3. If agent has Foundry backend:
       token_cost = (tokens_input * model.input_per_1m / 1_000_000)
                  + (tokens_output * model.output_per_1m / 1_000_000)
                  - (tokens_cached * model.input_per_1m * 0.90 / 1_000_000)  # cached 10%
       if batch_api: token_cost *= 0.50
    
    4. CRITICAL: Hybrid de-dup
       If agent_type == HYBRID_STUDIO_FOUNDRY:
           total = license_cost + credits_cost + azure_cost  # ALL THREE sum up
           # Credits cover Studio orchestration
           # Azure tokens cover Foundry inference
           # NEVER choose one over the other
    
    5. Per utilisation band:
       low = base * 0.75
       expected = base * 1.00
       high = base * 1.25
    
    6. Unit economics:
       cost_per_interaction = total_monthly / (total_users * interactions_per_user)
       cost_per_active_user = total_monthly / active_users
    """

class ScenarioComparison:
    """
    Compare multiple agent design options side-by-side.
    Input: list[AgentProfile] with same user_population and interaction_volume.
    Output: ranked list of (profile, cost_breakdown) sorted by total_monthly_usd.
    Also: technology_recommendation with justification text citing rate card rules.
    
    Include scenarios for all realistic agent_types:
      1. declarative_instruction (free tier)
      2. declarative_tenant (M365 orchestrator + credits)
      3. copilot_studio_custom (full Studio, PAYG/pack)
      4. foundry_native (tokens only)
      5. foundry_hosted (compute + tokens)
      6. hybrid_studio_foundry (both meters)
    
    Generate recommendation matrix:
      - Cheapest option for: (a) all-licensed users, (b) mixed population, (c) all-unlicensed
      - Note crossover point: "Copilot Studio is cheaper than Foundry until X token/month"
    """
```

### 6.4 Module 4 — Optimisation Engine

```python
# src/optimisation/recommender.py

OPTIMISATION_RULES: list[OptimisationRule] = [
    OptimisationRule(
        category=OptimisationCategory.LICENSE_CHANNEL_ROUTING,
        title="Move licensed users to M365 channel for zero-rated credits",
        priority=1,
        # Trigger: agent has licensed users on non-M365 channel paying credits
        trigger=lambda a, costs: (
            a.licensed_user_count > 0
            and a.channel not in [Channel.M365_COPILOT, Channel.TEAMS_COPILOT_EXTENSION]
            and costs.credits_charged > 0
        ),
        # Saving: all credits currently charged for licensed users become zero-rated
        compute_saving=lambda a, costs, rates: (
            costs.credits_licensed_users_charged * rates.payg_per_credit
        ),
        effort="medium",
        evidence="B2E zero-rating rule — learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management",
    ),
    OptimisationRule(
        category=OptimisationCategory.MODEL_DOWNSHIFT,
        title="Route simple queries to GPT-4o-mini (16× cheaper input)",
        priority=2,
        trigger=lambda a, costs: (
            a.primary_model_id in ["gpt_4o", "gpt_5_4", "gpt_4_1"]
            and a.avg_tokens_input_per_interaction is not None
        ),
        compute_saving=lambda a, costs, rates: (
            # Assumes 60% of queries are "simple" and can be routed to mini
            0.60 * costs.azure_openai_cost_usd * (
                1 - rates.gpt_4o_mini.input_per_1m / rates.gpt_4o.input_per_1m
            )
        ),
        effort="medium",
        evidence="GPT-4o $2.50/1M input vs GPT-4o-mini $0.15/1M — azure.microsoft.com/pricing/details/azure-openai",
    ),
    OptimisationRule(
        category=OptimisationCategory.PROMPT_CACHING,
        title="Enable prompt caching (10× discount on repeated system prompts)",
        priority=3,
        trigger=lambda a, costs: (
            a.prompt_caching_enabled == False
            and a.avg_tokens_input_per_interaction is not None
            and a.primary_model_id in ["gpt_5_4", "gpt_5_4_mini", "gpt_5_4_nano", "gpt_4_1", "gpt_4_1_mini"]
        ),
        compute_saving=lambda a, costs, rates: (
            # System prompt typically 30-50% of input tokens; cached at 10% price
            0.40 * costs.azure_openai_cost_usd * (1 - 0.10)
        ),
        effort="low",
        evidence="Cached input = 10% of input price — azure.microsoft.com/pricing/details/azure-openai",
    ),
    OptimisationRule(
        category=OptimisationCategory.BATCH_API,
        title="Convert async workloads to Batch API (50% discount)",
        priority=4,
        trigger=lambda a, costs: (
            a.uses_batch_api == False
            and a.agent_type in [AgentType.FOUNDRY_NATIVE, AgentType.FOUNDRY_HOSTED]
            # Suitable for non-interactive: summarisation, classification, bulk embeddings
        ),
        compute_saving=lambda a, costs, rates: costs.azure_openai_cost_usd * 0.50,
        effort="medium",
        evidence="Batch API 50% discount — Global Standard only",
    ),
    OptimisationRule(
        category=OptimisationCategory.PTU_RESERVATION,
        title="Commit to Provisioned Throughput Units (PTU) — 30-50% saving",
        priority=5,
        trigger=lambda a, costs: (
            a.primary_model_id is not None
            and costs.tokens_monthly >= 2_000_000_000  # break-even for GPT-4o
        ),
        compute_saving=lambda a, costs, rates: costs.azure_openai_cost_usd * 0.40,
        effort="high",
        evidence="PTU break-even ~2B tokens/month (GPT-4o); 1-year reservation 50% off",
    ),
    OptimisationRule(
        category=OptimisationCategory.GRAPH_GROUNDING_TOGGLE,
        title="Disable tenant Graph grounding when public web suffices (saves 10 credits/event)",
        priority=6,
        trigger=lambda a, costs: (
            a.uses_tenant_graph == True
            and costs.credits_detail.get("tenant_graph_grounding", 0) > 500  # $5+/month
        ),
        compute_saving=lambda a, costs, rates: (
            costs.credits_detail["tenant_graph_grounding"] * rates.payg_per_credit
        ),
        effort="low",
        evidence="Tenant Graph grounding = 10 credits/event; public web grounding = free",
    ),
    OptimisationRule(
        category=OptimisationCategory.CLASSIC_ANSWER_FALLBACK,
        title="Use classic answers for FAQ topics (halves credit cost vs generative)",
        priority=7,
        trigger=lambda a, costs: (
            costs.credits_detail.get("generative_answer", 0) > 5000
        ),
        compute_saving=lambda a, costs, rates: (
            costs.credits_detail["generative_answer"] * 0.50 * rates.payg_per_credit
        ),
        effort="low",
        evidence="Classic = 1 credit, Generative = 2 credits — route FAQ topics to classic",
    ),
    OptimisationRule(
        category=OptimisationCategory.ZOMBIE_FT_MODEL,
        title="Decommission idle fine-tuned model ($1,836–$2,160/month when idle)",
        priority=8,
        trigger=lambda a, costs: (
            a.fine_tuned_model_id is not None
            # Checked by anomaly detector: <1 invocation/day for >7 days
        ),
        compute_saving=lambda a, costs, rates: Decimal("1836"),   # conservative floor
        effort="low",
        evidence="Fine-tuned model deployment cost: $1,836–$2,160/month regardless of usage",
    ),
    OptimisationRule(
        category=OptimisationCategory.PACK_VS_PAYG,
        title="Switch from PAYG to prepaid credit pack (20% saving)",
        priority=9,
        trigger=lambda a, costs: (
            costs.credits_recommendation == "payg"
            and costs.credits_charged >= 25000
        ),
        compute_saving=lambda a, costs, rates: (
            costs.credits_cost_payg_usd - costs.credits_cost_pack_usd
        ),
        effort="low",
        evidence="Pack: $200/25k credits ($0.008/credit) vs PAYG $0.01/credit — 20% saving",
    ),
    OptimisationRule(
        category=OptimisationCategory.LICENSE_RIGHT_SIZING,
        title="Right-size M365 Copilot licenses (3.3% average adoption; remove inactive seats)",
        priority=10,
        trigger=lambda a, costs: (
            a.licensed_user_count > 0
            and a.active_users_7d is not None
            and (a.active_users_7d / a.licensed_user_count) < 0.50
        ),
        compute_saving=lambda a, costs, rates: (
            (a.licensed_user_count - a.active_users_7d) * 30  # $30/unused seat
        ),
        effort="high",  # License reductions require procurement approval
        evidence="Microsoft global M365 Copilot adoption: 3.3% of commercial M365 seats (Q1 2026)",
    ),
    OptimisationRule(
        category=OptimisationCategory.AGENT_TECHNOLOGY_SWITCH,
        title="Switch to instruction-only declarative agent (free for all users)",
        priority=11,
        trigger=lambda a, costs: (
            a.agent_type in [AgentType.COPILOT_STUDIO_CUSTOM, AgentType.DECLARATIVE_TENANT]
            and a.uses_tenant_graph == False
            and a.uses_ai_search == False
        ),
        compute_saving=lambda a, costs, rates: costs.credits_cost_payg_usd,
        effort="medium",
        evidence="Declarative instruction/public agents = $0 for ALL users (licensed and unlicensed)",
    ),
]
```

### 6.5 Module 5 — Governance

```python
# src/governance/budgets.py
"""
Budget configuration mirrors Azure Cost Management + M365 admin center billing policies.

Budget types:
  1. Azure subscription budget (enforced via Azure Cost Management REST API)
     - Scope: subscription, resource group, or tag-based
     - Alert thresholds: 80%, 100%, forecast 100%
     - Actions: email, Action Group (webhook → PagerDuty / Teams)
  
  2. M365 billing policy budget (M365 admin center)
     - Scope: per billing policy (maps to Copilot Credits allocation)
     - Alert threshold: 2,000 credits per user per day
     - NOTE: alerts only — do NOT cap agent spend automatically (agents keep running)
  
  3. Application-level budget (internal to this app)
     - Defined per agent, per cost centre, per environment
     - Alert when actual > 80% of budget AND forecast > 100%

Budget enforcement policy:
  For AI workloads, NEVER hard-stop an agent on budget breach without human approval.
  Use budget alerts + human-in-loop approval workflow (Teams adaptive card).
"""

# src/governance/anomaly_detector.py
"""
ML-based anomaly detection for AI spend.

Detectors:
  1. Daily token spike: actual > (rolling_30d_mean + 2 * rolling_30d_std) → ALERT
  2. Credit burst: single user > 2,000 credits/day → ALERT
  3. Zombie fine-tuned model: deployed_days > 7 AND daily_invocations < 1 → CRITICAL
  4. Idle endpoint: endpoint_deployed_days > 7 AND weekly_requests == 0 → WARNING
  5. Untagged spend: cost_row missing required tag → FIX-IT
  6. Grounding cost spike: tenant_graph_grounding credits > 2σ → ALERT
  7. Pack exhaustion: credits_remaining < 10% of pack AND >10 days left in month → WARNING
  8. New AI service: new Azure resource type in AI category, not in known-agents registry → REVIEW
  9. Agent not in Agent 365 registry: Copilot Studio / Foundry agent found in prod but not registered → GOVERNANCE
  10. M365 Frontier preview pricing: agent has is_frontier_preview=True AND in production → COST RISK

All anomalies emit to:
  - Anomaly table in database
  - Teams notification (via Power Automate or Graph API) to agent owner
  - Weekly governance digest email to CostCenter owners
"""

# src/governance/reporting.py
"""
Reporting outputs:

1. Executive summary (monthly)
   - Total AI spend by meter (pie: license vs credits vs azure)
   - Month-over-month trend
   - Top 5 agents by cost
   - Top 3 optimisation opportunities with $ impact

2. Agent cost ledger (operational)
   - Per-agent: actual vs budget, credits vs azure, licensed vs unlicensed user costs
   - Sortable by: total cost, cost/interaction, growth rate, optimisation potential

3. License utilisation report
   - M365 Copilot seats assigned vs active (7d, 30d)
   - Shadow credits (what unlicensed-channel usage would have cost)
   - Recommendation: seats to reclaim vs seats to reassign

4. Technology decision report
   - For each agent: current cost, cheapest viable alternative, switching cost estimate
   - Break-even analysis: at what interaction volume does Foundry beat Copilot Studio?

5. Commitment planning
   - PTU break-even tracker (month-by-month tokens vs break-even threshold)
   - Credit pack ROI (PAYG effective rate vs pack effective rate)
   - MACC drawdown tracker (Azure commitment consumption)

6. FOCUS export
   - Standard FOCUS 1.1 format for FinOps tool interoperability (Apptio, CloudHealth, etc.)
   - Exported weekly to Azure Data Lake Storage

Power BI integration:
  - Publish semantic model to Fabric workspace
  - Pre-built measures: TotalAICost, CostPerInteraction, CreditEfficiency, LicenceUtilisation
  - Row-level security by CostCenter
"""
```

---

## 7. API Design

All routes are REST JSON. Authentication via Entra ID (Bearer token). Scopes: `api://ai-finops/CostViewer`, `api://ai-finops/CostAdmin`.

```
GET  /api/v1/agents                          List all agents with current month cost summary
GET  /api/v1/agents/{agent_id}               Full agent profile + latest cost breakdown
POST /api/v1/agents/{agent_id}/estimate      Run what-if estimate (body: usage assumptions)
POST /api/v1/scenarios/compare               Compare N agent designs side-by-side
GET  /api/v1/cost/ledger                     Paginated cost events (filter: date, agent, meter, cost_center)
GET  /api/v1/cost/summary                    Aggregated totals by meter, period, groupBy
GET  /api/v1/cost/trends                     Time-series data for charts
GET  /api/v1/optimisations                   All active recommendations ranked by saving
POST /api/v1/optimisations/{id}/dismiss      Dismiss a recommendation with reason
GET  /api/v1/licenses                        License assignment summary + utilisation stats
GET  /api/v1/credits                         Copilot Credits usage (period, agent breakdown)
GET  /api/v1/budgets                         All budgets with current consumption %
POST /api/v1/budgets                         Create/update a budget
GET  /api/v1/anomalies                       Active anomalies with severity
POST /api/v1/anomalies/{id}/acknowledge      Acknowledge + set follow-up action
GET  /api/v1/rate-cards                      Current rate card values (read-only)
GET  /api/v1/rate-cards/refresh-status       When each rate card was last refreshed
GET  /api/v1/reports/executive-summary       Monthly executive PDF/JSON
GET  /api/v1/reports/focus-export            FOCUS 1.1 download
GET  /api/v1/health                          Service health + last data ingestion timestamps
```

---

## 8. UI/UX Requirements

Build a single-page React application with five main views. Use Microsoft Fabric design tokens (fluent colours) but do not depend on the Fluent UI component library — use shadcn/ui with a custom Fabric-compatible theme.

### 8.1 Dashboard (Home)

**Purpose:** Instant overview of AI spend health.

Layout: header KPI strip + 2-column main area

KPI strip (4 cards):
- **Total AI Spend This Month** — actual vs budget, % change MoM
- **Copilot Credits Billed** — charged credits + shadow credits; pack fill %
- **Azure Consumption** — token spend by top model
- **Optimisation Potential** — total monthly savings identified, # recommendations

Main area left (60%): 
- AI Spend by Meter — stacked area chart (License / Credits / Azure) over 6 months
- Top 5 Agents by Cost — horizontal bar chart with cost-per-interaction annotation

Main area right (40%):
- Credit pool ring chart: pack used / remaining / PAYG overflow
- Anomaly alert list (latest 5, colour-coded severity)
- License utilisation gauge: assigned vs active Copilot seats

### 8.2 Agent Explorer

**Purpose:** Drill into any agent's cost anatomy.

Top filter bar: date range | environment | cost centre | agent type
Agent table columns: Agent Name | Type | Channel | Monthly Cost | Cost/Interaction | Credits Used | Tokens Used | Optimisation Score | Status

On row click → Agent Detail panel (slide-in):
- Cost timeline (bar chart: daily cost by meter)
- Credit breakdown (pie: classic / generative / grounding / actions / flows / ai tools)
- Token breakdown (model, input/output/cached ratio)
- User population (licensed / unlicensed / external split with cost per segment)
- Active recommendations (collapsible)
- Technical profile (read-only display of AgentProfile fields)

### 8.3 What-If Modeler

**Purpose:** Model agent costs before building. Primary tool for technology decisions.

**Step 1 — Agent Configuration**
Form fields:
- Agent name (free text)
- Agent type (dropdown: declarative_instruction / declarative_public / declarative_tenant / copilot_studio_custom / foundry_native / foundry_hosted / hybrid_studio_foundry)
- Channel (dropdown)
- Uses tenant Graph grounding? (toggle — immediately shows/hides the 10-credit/event field)
- Primary model (dropdown, shown only for Foundry types)
- Prompt caching enabled? (toggle with estimated saving shown inline)
- Reasoning model? (toggle — shows premium AI tools stacking note)

**Step 2 — User Population**
- Licensed users count + avg interactions/month/user
- Unlicensed users count + avg interactions/month/user
- External users count + avg interactions/month/user
- Period (3/6/12 months)

**Step 3 — Interaction Profile**
For Copilot Credits (auto-shown for declarative/Studio types):
- Sliders: classic answers per interaction, generative answers, agent actions, tenant graph grounding events, agent flow actions (per 100), AI tool tier (basic/standard/premium), content pages

For Azure consumption (auto-shown for Foundry types):
- Avg tokens input per interaction
- Avg tokens output per interaction
- Cache hit rate % (slider)

**Results panel** (live as inputs change):
- CostBreakdown card with all three meters
- Utilisation sensitivity band (low/expected/high)
- "Compare vs alternatives" — auto-generates comparison table for all viable agent types given same inputs
- Technology recommendation callout with justification
- Export to PDF button

### 8.4 Optimisations

**Purpose:** Ranked action list to reduce AI spend.

Filter: category | effort | min saving
Sort: saving desc (default) | effort asc | category

Recommendation card:
- Title + category badge
- Before vs After cost comparison (USD/month)
- Effort badge (Low/Medium/High)
- Confidence score
- Justification text (cite rate card rule)
- "Take action" link (opens Microsoft docs or admin portal in new tab)
- "Dismiss" button with reason dropdown (not applicable / already done / future consideration)

Total saving summary at top: "Implementing all Low-effort recommendations saves $X/month"

### 8.5 Governance

Tabs:
- **Budgets** — table of all budgets with consumption bar + alerts configuration
- **Anomalies** — sortable list, severity filter, acknowledge workflow
- **License Coverage** — grid showing each agent and its governance status (Agent 365 registered?, Owner assigned?, Tags complete?)
- **Rate Card Health** — table of all rate card files, last-refreshed timestamp, staleness alert if >7 days
- **FOCUS Export** — download link + export history

---

## 9. Integration Specifications

### 9.1 Microsoft Graph API (Credits + Licenses)

```python
# Required scopes (add to app registration manifest):
REQUIRED_GRAPH_SCOPES = [
    "Reports.Read.All",          # Copilot Credits usage report
    "User.Read.All",             # License assignments + sign-in activity
    "Directory.Read.All",        # Group membership for cost centre attribution
    "AgentRegistry.Read.All",    # Agent 365 registry (if tenant has Agent 365)
]

# Rate limiting: Microsoft Graph applies 10,000 requests/10 min per app
# Use $batch endpoint for bulk user license lookups (up to 20 per batch)
# Always handle 429 Retry-After headers with exponential backoff
```

### 9.2 Azure Cost Management API

```python
# FOCUS export setup (configure once per tenant via Bicep):
# - Export type: FOCUS 1.1
# - Scope: Management Group (recommended) or Subscription
# - Cadence: Daily
# - Destination: Storage Account container 'focus-exports'
# - Retention: 24 months

# For on-demand queries:
# POST /subscriptions/{subscriptionId}/providers/Microsoft.CostManagement/query
# Required role: Cost Management Reader on subscription

# Rate limits: 30 requests/minute per subscription; use SDK with built-in retry
```

### 9.3 Azure Retail Prices API (Rate Card Refresh)

```python
# Source of truth for current Azure pricing — poll weekly
# GET https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview
#   &$filter=serviceName eq 'Azure OpenAI' and armRegionName eq 'eastus'

# Map API response to rate card YAML fields
# Flag any model present in YAML but absent from API → alert for manual review
# Append new models found in API but absent from YAML → create draft rate card entry for review

# Copilot Credit rates do NOT appear in Azure Retail Prices API — only update from Microsoft Learn docs manually + confirm via admin center actuals
```

---

## 10. Testing Requirements

### 10.1 Regression Fixtures (from Microsoft Learn worked examples)

These must pass as unit tests — they document the core billing rules:

```python
# tests/fixtures/microsoft_learn_examples.py

def test_b2e_helpdesk_contractor_cost():
    """
    Source: Kim Brian 'Demystifying Copilot Studio Credits' LinkedIn
    200 unlicensed contractors × 300 conversations/month × 24 credits/conversation
    = 1,440,000 credits = $14,400/month PAYG
    """
    profile = AgentProfile(
        agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
        channel=Channel.TEAMS_STANDALONE,
        licensed_user_count=0,
        unlicensed_user_count=200,
        avg_interactions_per_user_per_month=300,
    )
    usage = InteractionProfile(
        generative_answers_per_interaction=2,
        agent_actions_per_interaction=1,
        tenant_graph_grounding_per_interaction=1,
    )
    result = CostCalculator().estimate(profile, usage, period_months=1)
    assert result.credits_charged == 1_440_000
    assert abs(result.credits_cost_payg_usd - Decimal("14400")) < Decimal("0.01")
    assert result.b2e_zero_rated is False

def test_b2e_licensed_user_zero_cost_on_m365_channel():
    """
    Same agent as above but user has M365 Copilot license AND is in M365 channel.
    Credit cost = $0. Shadow credits still recorded.
    """
    profile = AgentProfile(
        agent_type=AgentType.COPILOT_STUDIO_CUSTOM,
        channel=Channel.M365_COPILOT,
        licensed_user_count=500,
        unlicensed_user_count=0,
        avg_interactions_per_user_per_month=300,
    )
    usage = InteractionProfile(generative_answers_per_interaction=2, ...)
    result = CostCalculator().estimate(profile, usage, period_months=1)
    assert result.credits_cost_payg_usd == Decimal("0")
    assert result.credits_shadow > 0    # shadow credits recorded for utilisation

def test_declarative_free_tier_all_users():
    """
    Instruction-only declarative agent = $0 for ALL users (licensed or not).
    Source: Microsoft Docs cost-considerations.md
    """
    profile = AgentProfile(
        agent_type=AgentType.DECLARATIVE_INSTRUCTION,
        channel=Channel.COPILOT_CHAT_FREE,
        licensed_user_count=0,
        unlicensed_user_count=1000,
        avg_interactions_per_user_per_month=50,
        uses_tenant_graph=False,
        uses_public_web=True,
    )
    result = CostCalculator().estimate(profile, InteractionProfile(...), period_months=1)
    assert result.credits_cost_payg_usd == Decimal("0")
    assert result.credits_cost_pack_usd == Decimal("0")

def test_declarative_tenant_grounding_unlicensed_user():
    """
    Declarative agent + SharePoint grounding + unlicensed user
    = 10 credits (grounding) + 2 credits (generative) = 12 credits = $0.12 PAYG per interaction
    Source: Microsoft Docs cost-considerations.md
    """
    profile = AgentProfile(
        agent_type=AgentType.DECLARATIVE_TENANT,
        channel=Channel.COPILOT_CHAT_FREE,
        licensed_user_count=0,
        unlicensed_user_count=1,
        avg_interactions_per_user_per_month=1,
        uses_tenant_graph=True,
    )
    usage = InteractionProfile(
        generative_answers_per_interaction=1,
        tenant_graph_grounding_per_interaction=1,
    )
    result = CostCalculator().estimate(profile, usage, period_months=1)
    assert result.credits_charged == 12
    assert abs(result.credits_cost_payg_usd - Decimal("0.12")) < Decimal("0.001")

def test_reasoning_model_premium_stacks():
    """
    Agent using reasoning model: generative answer (2) + premium AI tool (100/10 = 10 per response)
    = 12 credits per interaction, NOT 100 credits (premium does not REPLACE generative — it ADDS)
    Source: Microsoft Learn billing rates note on stacking
    """
    usage = InteractionProfile(
        generative_answers_per_interaction=1,
        ai_tool_premium_responses_per_interaction=1,
    )
    result = CostCalculator().calculate_credits_per_interaction(usage)
    assert result["generative"] == 2
    assert result["ai_tools_premium"] == 10    # 100 credits / 10 responses
    assert result["total"] == 12              # stacked, not replaced

def test_hybrid_studio_foundry_both_meters_fire():
    """
    Copilot Studio agent calling a Foundry endpoint:
    BOTH Copilot Credits (Studio) AND Azure OpenAI tokens (Foundry) apply.
    """
    profile = AgentProfile(
        agent_type=AgentType.HYBRID_STUDIO_FOUNDRY,
        channel=Channel.M365_COPILOT,
        licensed_user_count=100,
        primary_model_id="gpt_4o",
        avg_tokens_input_per_interaction=2000,
        avg_tokens_output_per_interaction=500,
    )
    result = CostCalculator().estimate(profile, ...)
    # Even for licensed users (zero-rated credits), Azure tokens still bill
    assert result.credits_cost_payg_usd == Decimal("0")   # B2E zero-rated
    assert result.azure_openai_cost_usd > Decimal("0")    # tokens still billed
    assert result.total_monthly_usd == result.azure_openai_cost_usd  # only azure fires

def test_pack_vs_payg_threshold():
    """
    At exactly 25,000 credits: pack ($200) = PAYG ($250). Above → pack wins.
    """
    assert pack_cost(24999) > payg_cost(24999)    # PAYG cheaper below threshold
    assert pack_cost(25000) == payg_cost(25000)   # break-even
    assert pack_cost(25001) < payg_cost(25001)    # pack cheaper above
```

### 10.2 Integration Test Requirements

- Mock Microsoft Graph API (MSGraphMocker) and Azure Cost Management API (AzureCostMocker)
- Fixture: 3-month FOCUS export with realistic AI service rows
- End-to-end: ingest → allocate → compute breakdown → generate optimisations → assert recommendations ranked correctly
- Contract test: FOCUS export schema matches FOCUS 1.1 specification column definitions

### 10.3 UI Component Tests

- What-If modeler: change agent_type from copilot_studio_custom to declarative_instruction → cost should drop to $0 immediately
- B2E toggle: change channel from web_chat to m365_copilot → credit cost collapses to $0, shadow credits appear
- Rate card stale warning: set last_refreshed > 7 days → banner appears in governance tab

---

## 11. Coding Standards

### Python (backend)
- Async throughout: `async def` all I/O, `asyncio.gather()` for parallel Graph + Azure calls
- Never store dollar amounts as floats — use `Decimal` everywhere
- Type hints on all function signatures; mypy strict mode
- All rate card access via `RateCardService` (never direct YAML access in business logic)
- NEVER hardcode a dollar amount, credit rate, or pricing constant in Python/TypeScript files — reference by key from YAML

### TypeScript (frontend)
- Strict TypeScript — `"strict": true` in tsconfig
- All monetary values: `Decimal.js` (never native `number` for currency)
- Tanstack Query for all API calls; no manual fetch calls in components
- Chart labels: always include currency unit and time period

### Security
- Never log full user IDs or UPNs in application logs
- Cost data exports: apply Purview sensitivity label check before writing to ADLS
- All secrets in Azure Key Vault, accessed via Managed Identity
- CORS: restrict to tenant domain + localhost in dev only

### Rate card hygiene
- Every rate card file has `effective_date` and `source_url`
- `RateCardService` logs a WARNING if any rate card file has `effective_date` > 7 days ago
- Rate card refresh is idempotent — skip if new rates match stored rates

---

## 12. Deployment (Bicep)

Minimum Azure resources to provision:

```
Resource Group: rg-ai-finops-{env}
├── App Service Plan (B2 minimum, P1v3 for prod)
├── App Service (FastAPI backend)
├── Static Web App (React frontend)
├── Azure SQL Database (Standard S3 minimum for prod)
├── Azure Functions App (ingestion jobs)
├── Azure Service Bus (Namespace + Queues for async ingestion)
├── Azure Cache for Redis (C1 minimum)
├── Storage Account (FOCUS exports + rate card cache)
├── Azure Key Vault (secrets)
├── Managed Identity (system-assigned on App Service + Functions)
├── Application Insights (linked to all services)
└── App Configuration (feature flags + environment config)
```

Required RBAC assignments (Managed Identity):
- `Cost Management Reader` on subscription (for on-demand Cost Management queries)
- `Storage Blob Data Contributor` on FOCUS export storage account
- `Key Vault Secrets User` on Key Vault

Required Entra app registration permissions:
- `Reports.Read.All` (application, admin consent)
- `User.Read.All` (application, admin consent)
- `Directory.Read.All` (application, admin consent)

---

## 13. Known Constraints and Guard-Rails

1. **Rate cards as configuration**: Never commit a dollar amount to Python or TypeScript source. Every price lives in `config/rate_cards/*.yaml`. This is enforced by a CI lint step that blocks any PR containing patterns like `0.01` or `30.00` in `*.py` or `*.ts` files (outside test fixtures).

2. **Forward-looking pricing (MODERATE confidence)**:
   - M365 E3 rising to $39, E5 to $60 on 2026-07-01 — single-sourced; flag in UI as "projected"
   - Frontier preview features (App Builder, agentic users) — not GA-priced; always show as "[preview — pricing TBC]" in modeler outputs

3. **B2E fair-use limits**: Microsoft has not published explicit fair-use thresholds. The modeler must expose a configurable `b2e_fair_use_credits_per_user_per_month` parameter (default: None = unlimited). If Microsoft publishes limits, set this parameter without code change.

4. **FOCUS schema drift**: FOCUS 1.x → 2.x will rename columns. Wrap all FOCUS field access in an adapter class (`FocusRowAdapter`) so schema upgrades require only adapter changes.

5. **Agent 365 agentic users** (not yet GA): autonomous-agent identities with their own credentials will likely require per-agent licensing in 2027 per Microsoft roadmap. The `AgentProfile` already has `agent_365_registered: bool` — extend this to `agent_365_license_type` when GA.

6. **Double-counting in hybrid architectures**: When a Copilot Studio agent calls a Foundry endpoint, the Azure OpenAI tokens flow through the customer's Azure subscription — they appear in Cost Management FOCUS exports AND in the Copilot Studio Credit bill (as a credit event). The ingestion module must detect this pattern (same timestamp, same agent, both Credit and Token events) and flag for manual de-dup review rather than silently summing.

---

## 14. Glossary (embed in UI help tooltips)

| Term | Definition |
|------|-----------|
| Copilot Credits | Microsoft's unified consumption currency (1 credit = $0.01 PAYG) for Copilot Studio and declarative agents. Replaced "messages" Sep 2025. |
| B2E Zero-Rating | When an M365 Copilot-licensed user invokes an agent on the M365/Teams channel, their Copilot Credits cost is waived. The full-rate shadow still counts for utilisation reporting. |
| Declarative Agent | A customised version of M365 Copilot described in a JSON manifest. Runs on M365 orchestrator. Instruction-only and public-web variants cost $0 for all users. |
| Copilot Studio Custom Agent | An agent built on Copilot Studio's own orchestrator. Always metered in Copilot Credits (B2E zero-rated for licensed users in M365 channel). |
| Foundry Native Agent | An agent built in Azure AI Foundry; no runtime charge — pay only for Azure OpenAI tokens and tools. |
| Hosted Agent | An agent running on the Foundry hosted-agent runtime (customer-dedicated containers). Billed at $0.0994/vCPU-hr + $0.0118/GiB-hr. |
| PTU | Provisioned Throughput Units. Reserved Azure OpenAI capacity. Break-even vs PAYG: ~2B tokens/month for GPT-4o. |
| Agent 365 | Microsoft's governance control plane for AI agents ($15/user/month, GA May 2026). Does NOT include agent build/run cost. |
| M365 E7 Frontier Suite | $99/user/month bundle (E5 + M365 Copilot + Entra Suite + Agent 365), GA May 2026. |
| FOCUS | FinOps Open Cost & Usage Specification. Standard format for cloud billing data. Natively emitted by Azure Cost Management. |
| Shadow Credits | Credits that WOULD have been charged if not for B2E zero-rating. Always record for utilisation and what-if analysis. |

---

*Rate cards effective: 2026-05-12. Refresh weekly from Azure Retail Prices API. Forward-looking prices (E3/E5 July 2026 increase; Frontier preview features) are flagged MODERATE confidence and must not be presented to users as confirmed.*
