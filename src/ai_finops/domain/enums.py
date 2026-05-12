"""Core enumerations for the AI FinOps three-meter model.

See copilot-instructions.md §5.1.
"""
from __future__ import annotations

from enum import Enum


class Meter(str, Enum):
    """One of three primary meters. Every cost line belongs to exactly one."""

    PER_SEAT = "per_seat"
    COPILOT_CREDITS = "copilot_credits"
    AZURE_CONSUMPTION = "azure_consumption"


class AgentType(str, Enum):
    DECLARATIVE_INSTRUCTION = "declarative_instruction"   # Free for all users
    DECLARATIVE_PUBLIC = "declarative_public"             # Free for all users
    DECLARATIVE_TENANT = "declarative_tenant"             # Metered for unlicensed users
    COPILOT_STUDIO_CUSTOM = "copilot_studio_custom"       # Always metered, B2E zero-rated
    COPILOT_STUDIO_DECLARATIVE = "copilot_studio_declarative"
    FOUNDRY_NATIVE = "foundry_native"                     # Azure consumption only
    FOUNDRY_HOSTED = "foundry_hosted"                     # Azure compute + tokens
    HYBRID_STUDIO_FOUNDRY = "hybrid_studio_foundry"       # Both meters fire


class Channel(str, Enum):
    M365_COPILOT = "m365_copilot"          # B2E zero-rating applies
    TEAMS_COPILOT_EXTENSION = "teams_copilot_extension"  # B2E zero-rating applies
    TEAMS_STANDALONE = "teams_standalone"
    WEB_CHAT = "web_chat"
    CUSTOM_CHANNEL = "custom_channel"
    COPILOT_CHAT_FREE = "copilot_chat_free"


class UserLicenseType(str, Enum):
    M365_COPILOT_LICENSED = "m365_copilot_licensed"
    M365_COPILOT_E7 = "m365_copilot_e7"
    INTERNAL_UNLICENSED = "internal_unlicensed"
    CONTRACTOR = "contractor"
    EXTERNAL_CUSTOMER = "external_customer"
    ANONYMOUS = "anonymous"


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


# B2E channels and agent types eligible for zero-rating (mirrors copilot_credits.yaml).
B2E_ELIGIBLE_CHANNELS: frozenset[Channel] = frozenset(
    {Channel.M365_COPILOT, Channel.TEAMS_COPILOT_EXTENSION}
)
B2E_ELIGIBLE_AGENT_TYPES: frozenset[AgentType] = frozenset(
    {
        AgentType.DECLARATIVE_INSTRUCTION,
        AgentType.DECLARATIVE_PUBLIC,
        AgentType.DECLARATIVE_TENANT,
        AgentType.COPILOT_STUDIO_CUSTOM,
        AgentType.COPILOT_STUDIO_DECLARATIVE,
    }
)
B2E_LICENSED_USER_TYPES: frozenset[UserLicenseType] = frozenset(
    {UserLicenseType.M365_COPILOT_LICENSED, UserLicenseType.M365_COPILOT_E7}
)
DECLARATIVE_FREE_TIER_AGENT_TYPES: frozenset[AgentType] = frozenset(
    {AgentType.DECLARATIVE_INSTRUCTION, AgentType.DECLARATIVE_PUBLIC}
)
