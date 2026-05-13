"""SQLAlchemy 2.0 ORM models for the AI FinOps cost ledger."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class AgentRow(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(256), default="")
    agent_type: Mapped[str] = mapped_column(String(64), default="declarative_instruction")
    channel: Mapped[str] = mapped_column(String(64), default="m365_copilot")
    build_platform: Mapped[str] = mapped_column(String(64), default="")
    owner: Mapped[str] = mapped_column(String(256), default="")
    cost_center: Mapped[str] = mapped_column(String(128), default="")
    environment: Mapped[str] = mapped_column(String(32), default="prod")
    status: Mapped[str] = mapped_column(String(32), default="production")
    is_frontier_preview: Mapped[bool] = mapped_column(Boolean, default=False)

    uses_tenant_graph: Mapped[bool] = mapped_column(Boolean, default=False)
    uses_public_web: Mapped[bool] = mapped_column(Boolean, default=False)
    uses_dataverse: Mapped[bool] = mapped_column(Boolean, default=False)
    uses_ai_search: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_search_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_search_units: Mapped[int] = mapped_column(Integer, default=0)

    primary_model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reasoning_model: Mapped[bool] = mapped_column(Boolean, default=False)
    uses_batch_api: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_caching_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    fine_tuned_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    hosted_vcpu: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    hosted_memory_gib: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    hosted_hours_per_month: Mapped[int] = mapped_column(Integer, default=0)

    web_search_transactions: Mapped[int] = mapped_column(Integer, default=0)
    custom_search_transactions: Mapped[int] = mapped_column(Integer, default=0)
    code_interpreter_sessions: Mapped[int] = mapped_column(Integer, default=0)
    file_search_storage_gb: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    avg_credits_per_interaction: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    avg_tokens_input_per_interaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_tokens_output_per_interaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_interactions_per_user_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0)

    licensed_user_count: Mapped[int] = mapped_column(Integer, default=0)
    unlicensed_user_count: Mapped[int] = mapped_column(Integer, default=0)
    external_user_count: Mapped[int] = mapped_column(Integer, default=0)
    active_users_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agent_365_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_365_owner_upn: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CostEventRow(Base):
    __tablename__ = "cost_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    meter: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    agent_name: Mapped[str] = mapped_column(String(256), default="")
    agent_type: Mapped[str] = mapped_column(String(64), default="")
    channel: Mapped[str] = mapped_column(String(64), default="")
    user_license_type: Mapped[str] = mapped_column(String(64), default="")

    cost_center: Mapped[str] = mapped_column(String(128), index=True, default="")
    owner: Mapped[str] = mapped_column(String(256), default="")
    environment: Mapped[str] = mapped_column(String(32), default="prod")
    application: Mapped[str] = mapped_column(String(128), default="")

    credits_consumed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_shadow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b2e_zero_rated: Mapped[bool] = mapped_column(Boolean, default=False)

    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_cached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    azure_service: Mapped[str | None] = mapped_column(String(64), nullable=True)
    azure_resource_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    sku_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_users_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cost_actual_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    cost_shadow_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    discount_applied_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))

    source_system: Mapped[str] = mapped_column(String(64), default="")
    focus_billing_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


Index("ix_cost_events_meter_ts", CostEventRow.meter, CostEventRow.timestamp)
Index("ix_cost_events_agent_ts", CostEventRow.agent_id, CostEventRow.timestamp)


class OptimisationRow(Base):
    __tablename__ = "optimisations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    agent_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    monthly_saving_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    implementation_effort: Mapped[str] = mapped_column(String(16), default="medium")
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0)
    before_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    after_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    evidence: Mapped[str] = mapped_column(Text, default="")
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dismissed_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BudgetRow(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    period: Mapped[str] = mapped_column(String(16), default="monthly")
    alert_threshold_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=80)
    scope: Mapped[str] = mapped_column(String(256), default="")
    owner: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnomalyRow(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    detector: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    affected_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    affected_agent_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expected_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    actual_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    deviation_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acknowledged_action: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UntaggedSpendRow(Base):
    __tablename__ = "untagged_spend"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resource_id: Mapped[str] = mapped_column(String(512), default="")
    resource_name: Mapped[str] = mapped_column(String(256), default="")
    service_name: Mapped[str] = mapped_column(String(128), default="")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    missing_tags: Mapped[str] = mapped_column(String(512), default="")
    billing_period: Mapped[str | None] = mapped_column(String(32), nullable=True)


# =====================================================================
# Plug-and-play ingestion: tenant-discovery tables
# =====================================================================
class AgentOwnerRow(Base):
    """Owner identities for an Agent 365 / Entra agent."""

    __tablename__ = "agent_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    owner_upn: Mapped[str] = mapped_column(String(256), default="")
    owner_object_id: Mapped[str] = mapped_column(String(128), default="")
    owner_display_name: Mapped[str] = mapped_column(String(256), default="")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


Index(
    "ix_agent_owners_agent_object",
    AgentOwnerRow.agent_id, AgentOwnerRow.owner_object_id, unique=True,
)


class LicensedPopulationRow(Base):
    """One row per Copilot SKU snapshot — assigned + active counts."""

    __tablename__ = "licensed_population"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[str] = mapped_column(String(64), index=True)
    sku_part_number: Mapped[str] = mapped_column(String(128), default="")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    assigned_users: Mapped[int] = mapped_column(Integer, default=0)
    active_users_30d: Mapped[int] = mapped_column(Integer, default=0)
    active_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class DataSensitivityLabelRow(Base):
    """Purview sensitivity-label catalogue snapshot."""

    __tablename__ = "data_sensitivity_labels"

    label_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    sensitivity: Mapped[str] = mapped_column(String(32), default="internal", index=True)
    tooltip: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    dlp_policy_count: Mapped[int] = mapped_column(Integer, default=0)
    classification_count: Mapped[int] = mapped_column(Integer, default=0)
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class AgentRiskSignalRow(Base):
    """Defender / Security alert attributed to an agent service principal."""

    __tablename__ = "agent_risk_signals"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    alert_id: Mapped[str] = mapped_column(String(256), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="newAlert")
    category: Mapped[str] = mapped_column(String(64), default="")
    service_source: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class PowerPlatformEnvironmentRow(Base):
    """Snapshot of a Power Platform environment."""

    __tablename__ = "power_platform_environments"

    environment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    sku: Mapped[str] = mapped_column(String(64), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_pool_total: Mapped[int] = mapped_column(Integer, default=0)
    credit_pool_consumed: Mapped[int] = mapped_column(Integer, default=0)
    dlp_policy_count: Mapped[int] = mapped_column(Integer, default=0)
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class AzureInventoryRow(Base):
    """Snapshot of Azure resources gathered from ARM."""

    __tablename__ = "azure_inventory"

    resource_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    name: Mapped[str] = mapped_column(String(256), default="")
    kind: Mapped[str] = mapped_column(String(64), default="other", index=True)
    resource_type: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(64), default="")
    sku_name: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[str] = mapped_column(String(512), default="")
    subscription_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_system: Mapped[str] = mapped_column(String(64), default="")
    raw_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)


class IngestionRunRow(Base):
    """Audit table — one row per puller run (for the data-sources health UI)."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    sdk_call: Mapped[str] = mapped_column(String(512), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    untagged_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# =====================================================================
# Modeller — requirement-driven design surface (Part 2)
# =====================================================================
class AgentRequirementRow(Base):
    """A captured business requirement (free-text + structured form)."""

    __tablename__ = "agent_requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(32), default="employees")
    audience_size: Mapped[int] = mapped_column(Integer, default=0)
    data_sensitivity: Mapped[str] = mapped_column(String(32), default="internal")
    must_ground_on: Mapped[str] = mapped_column(String(256), default="")          # csv
    tools_required: Mapped[str] = mapped_column(String(256), default="")          # csv
    latency_target_ms: Mapped[int] = mapped_column(Integer, default=0)
    compliance_constraints: Mapped[str] = mapped_column(String(512), default="")  # csv
    expected_interactions_per_user_per_month: Mapped[int] = mapped_column(Integer, default=20)


class ModelerSessionRow(Base):
    """Persistent state of a modeller session (seed → refine → promote)."""

    __tablename__ = "modeler_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    last_score_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
