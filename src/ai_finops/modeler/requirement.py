"""Structured business requirement + deterministic free-text parser.

Part 2 §1 — the requirement is the only input to the seeder. The parser is a
deterministic rule extractor (regex + keyword + Purview-label lookup); no LLM
is in the decision path. An LLM may be wired in later as a *parser* whose
output the user must explicitly confirm before it reaches the seeder.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------
# Domain enums (kept as string constants for clarity in YAML matrices).
# ---------------------------------------------------------------------
AUDIENCES = ("employees", "customers", "mixed")
SENSITIVITIES = ("public", "internal", "confidential", "restricted")
GROUNDING_KINDS = ("sharepoint", "graph", "dataverse", "web", "custom_api")
TOOL_KINDS = ("lookup", "write_back", "workflow_trigger")


@dataclass
class AgentRequirement:
    """Structured form of a business requirement."""

    id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")
    description: str = ""
    audience: str = "employees"          # employees | customers | mixed
    audience_size: int = 0
    data_sensitivity: str = "internal"   # public | internal | confidential | restricted
    must_ground_on: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    latency_target_ms: int = 0
    compliance_constraints: list[str] = field(default_factory=list)
    expected_interactions_per_user_per_month: int = 20

    def to_db_fields(self) -> dict[str, Any]:
        """Flatten to the AgentRequirementRow column layout."""
        return {
            "id": self.id,
            "description": self.description,
            "audience": self.audience,
            "audience_size": self.audience_size,
            "data_sensitivity": self.data_sensitivity,
            "must_ground_on": ",".join(self.must_ground_on),
            "tools_required": ",".join(self.tools_required),
            "latency_target_ms": self.latency_target_ms,
            "compliance_constraints": ",".join(self.compliance_constraints),
            "expected_interactions_per_user_per_month": self.expected_interactions_per_user_per_month,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> AgentRequirement:
        return cls(
            id=str(row.get("id") or ""),
            description=str(row.get("description") or ""),
            audience=str(row.get("audience") or "employees"),
            audience_size=int(row.get("audience_size") or 0),
            data_sensitivity=str(row.get("data_sensitivity") or "internal"),
            must_ground_on=[s for s in str(row.get("must_ground_on") or "").split(",") if s],
            tools_required=[s for s in str(row.get("tools_required") or "").split(",") if s],
            latency_target_ms=int(row.get("latency_target_ms") or 0),
            compliance_constraints=[
                s for s in str(row.get("compliance_constraints") or "").split(",") if s
            ],
            expected_interactions_per_user_per_month=int(
                row.get("expected_interactions_per_user_per_month") or 20
            ),
        )


# ---------------------------------------------------------------------
# Deterministic free-text parser
# ---------------------------------------------------------------------
class RequirementParser:
    """Map a free-text description to a structured AgentRequirement.

    Pure-function, deterministic — same input → same output. Recognised
    keywords/regex are intentionally simple and listed here so a reviewer
    can audit them in one screen.
    """

    AUDIENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
        "employees": ("employee", "internal", "staff", "helpdesk", "ticket"),
        "customers": ("customer", "client", "external chat", "consumer", "shopper"),
        "mixed":     ("partners", "external + internal", "mixed audience"),
    }

    SENSITIVITY_KEYWORDS: dict[str, tuple[str, ...]] = {
        "restricted":   ("restricted", "regulated", "pii+phi", "secret"),
        "confidential": ("confidential", "policy", "hr", "finance", "legal"),
        "internal":     ("internal only", "intranet"),
        "public":       ("public", "marketing site", "open data"),
    }

    GROUNDING_KEYWORDS: dict[str, tuple[str, ...]] = {
        "sharepoint": ("sharepoint", "spo", "intranet pages"),
        "graph":      ("graph api", "microsoft graph", "calendar", "outlook"),
        "dataverse":  ("dataverse", "dynamics", "model-driven app"),
        "web":        ("public web", "bing", "internet search"),
        "custom_api": ("custom api", "rest api", "internal api", "back-office system"),
    }

    TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
        "lookup":           ("lookup", "answer questions", "cite", "search"),
        "write_back":       ("write-back", "create ticket", "update", "post message"),
        "workflow_trigger": ("trigger flow", "kick off", "approval", "automation"),
    }

    AUDIENCE_SIZE_RE = re.compile(r"(\d[\d,_ ]*)\s*(?:employees|users|customers|seats|people)", re.I)
    INTERACTIONS_RE = re.compile(
        r"(\d{1,4})\s*(?:interactions?|chats?|asks?)\s*(?:per|/)?\s*(?:user|month)",
        re.I,
    )
    LATENCY_RE = re.compile(r"(?:latency|respond|response)[^\d]{0,12}(\d{2,5})\s*(ms|s|sec|seconds)", re.I)

    COMPLIANCE_KEYWORDS: tuple[str, ...] = (
        "gdpr", "hipaa", "soc2", "iso27001", "pci-dss", "fedramp",
    )

    def parse(self, text: str) -> AgentRequirement:
        req = AgentRequirement(description=text)
        lowered = text.lower()

        # Audience — first match wins; order is "specific → generic".
        for audience, keywords in self.AUDIENCE_KEYWORDS.items():
            if any(k in lowered for k in keywords):
                req.audience = audience
                break

        # Sensitivity — high-to-low so 'restricted' wins over 'internal'.
        for sensitivity, keywords in self.SENSITIVITY_KEYWORDS.items():
            if any(k in lowered for k in keywords):
                req.data_sensitivity = sensitivity
                break

        # Grounding — additive.
        for kind, keywords in self.GROUNDING_KEYWORDS.items():
            if any(k in lowered for k in keywords):
                if kind not in req.must_ground_on:
                    req.must_ground_on.append(kind)

        # Tools — additive.
        for tool, keywords in self.TOOL_KEYWORDS.items():
            if any(k in lowered for k in keywords):
                if tool not in req.tools_required:
                    req.tools_required.append(tool)

        # Audience size.
        match = self.AUDIENCE_SIZE_RE.search(text)
        if match:
            digits = re.sub(r"[^\d]", "", match.group(1))
            req.audience_size = int(digits) if digits else 0

        # Interactions.
        match = self.INTERACTIONS_RE.search(text)
        if match:
            req.expected_interactions_per_user_per_month = int(match.group(1))

        # Latency target.
        match = self.LATENCY_RE.search(text)
        if match:
            value = int(match.group(1))
            unit = match.group(2).lower()
            if unit.startswith("s"):
                value *= 1000
            req.latency_target_ms = value

        # Compliance constraints — additive substring match.
        for kw in self.COMPLIANCE_KEYWORDS:
            if kw in lowered and kw not in req.compliance_constraints:
                req.compliance_constraints.append(kw)

        return req


def parse_free_text(text: str) -> AgentRequirement:
    """Module-level convenience: ``parse_free_text("...") -> AgentRequirement``."""
    return RequirementParser().parse(text)
