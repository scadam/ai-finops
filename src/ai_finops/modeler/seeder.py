"""TechnologySeeder — requirement → seeded AgentProfile + InteractionProfile.

Reads ``config/modeler/decision_matrix.yaml`` (a tenant-overridable artefact),
then optionally consumes tenant facts gathered by Part 1 pullers so the seed
is *real* for the tenant — e.g. the ``m365_copilot`` channel is suppressed
if zero E5+Copilot licenses exist.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..domain.enums import AgentType, Channel
from ..domain.models import AgentProfile, InteractionProfile
from .requirement import AgentRequirement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
@dataclass
class SeededAxis:
    """Annotated value on the editable design surface (Part 2 §3)."""

    value: Any
    locked: bool = False
    source: str = "seed"           # "seed" | "user" | "tenant_fact"
    rationale_id: str | None = None


@dataclass
class SeededDesign:
    """Bag of editable axes + the underlying typed AgentProfile/usage."""

    requirement_id: str
    profile: AgentProfile
    usage: InteractionProfile
    axes: dict[str, SeededAxis] = field(default_factory=dict)
    rationale_id: str | None = None
    rationale: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    available_channels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------
class TechnologySeeder:
    """Deterministic seeder driven by the YAML decision matrix."""

    def __init__(
        self,
        matrix_path: Path | str = "config/modeler/decision_matrix.yaml",
        matrix: dict[str, Any] | None = None,
    ) -> None:
        self._matrix_path = Path(matrix_path)
        if matrix is not None:
            self._matrix = matrix
        else:
            self._matrix = self._load(self._matrix_path)

    # --------------------------------------------------------------
    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(
                f"decision matrix not found at {path}; copy the shipped default."
            )
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} did not parse to a mapping")
        return data

    # --------------------------------------------------------------
    @property
    def rationales(self) -> dict[str, dict[str, str]]:
        return self._matrix.get("rationales") or {}

    @property
    def cells(self) -> list[dict[str, Any]]:
        return list(self._matrix.get("cells") or [])

    @property
    def capabilities(self) -> dict[str, dict[str, list[str]]]:
        return self._matrix.get("capabilities") or {}

    @property
    def channel_requires_sku(self) -> dict[str, str]:
        return self._matrix.get("channel_requires_sku") or {}

    @property
    def compliance_sensitivity(self) -> dict[str, list[str]]:
        return self._matrix.get("compliance_sensitivity") or {}

    # --------------------------------------------------------------
    @staticmethod
    def _matches(when: dict[str, Any], req: AgentRequirement) -> bool:
        """A cell matches when every key in ``when`` matches the requirement.

        * Wildcard ``"*"`` matches any value.
        * For *list* requirement axes (``must_ground_on``, ``tools_required``):
          the cell matches if ANY value listed in the cell appears in the
          requirement's list. (Cells that need a strict combination must
          state it as multiple separate keys instead.)
        * For *scalar* requirement axes the value must equal the requirement
          (case-insensitive) or be a list whose entries equal the requirement.
        """
        for key, expected in when.items():
            if expected == "*":
                continue
            actual = getattr(req, key, None)
            if isinstance(actual, list):
                actual_lc = {str(a).lower() for a in actual}
                if isinstance(expected, list):
                    expected_lc = {str(e).lower() for e in expected}
                    if not expected_lc & actual_lc:
                        return False
                else:
                    if str(expected).lower() not in actual_lc:
                        return False
            else:
                if isinstance(expected, list):
                    if str(actual or "").lower() not in {str(e).lower() for e in expected}:
                        return False
                else:
                    if str(actual or "").lower() != str(expected).lower():
                        return False
        return True

    # --------------------------------------------------------------
    def seed(
        self,
        req: AgentRequirement,
        tenant_facts: TenantFacts | None = None,
    ) -> SeededDesign:
        cell = self._first_match(req)
        then = cell.get("then", {})

        agent_type = AgentType(then.get("agent_type", AgentType.DECLARATIVE_PUBLIC.value))
        channel_str = then.get("channel", Channel.M365_COPILOT.value)
        rationale_id = then.get("rationale_id")
        rationale_obj = self.rationales.get(rationale_id or "", {})

        # ----- Tenant-aware channel constraint -----
        notes: list[str] = []
        available_channels = self._available_channels(tenant_facts)
        if available_channels and channel_str not in available_channels:
            notes.append(
                f"Seeded channel '{channel_str}' is not available in this tenant; "
                f"falling back to '{available_channels[0]}'."
            )
            channel_str = available_channels[0]
        channel = Channel(channel_str)

        # ----- Build profile -----
        profile = AgentProfile(
            agent_id=req.id,
            agent_name=f"Seeded for {req.id}",
            agent_type=agent_type,
            channel=channel,
            build_platform=str(then.get("build_platform") or "agents_toolkit"),
            uses_tenant_graph="sharepoint" in req.must_ground_on or "graph" in req.must_ground_on,
            uses_dataverse="dataverse" in req.must_ground_on,
            uses_public_web="web" in req.must_ground_on,
            licensed_user_count=self._licensed_seed(req, tenant_facts),
            unlicensed_user_count=max(
                0, req.audience_size - self._licensed_seed(req, tenant_facts)
            ),
            avg_interactions_per_user_per_month=req.expected_interactions_per_user_per_month,
        )
        usage = InteractionProfile(
            generative_answers_per_interaction=1.0,
            tenant_graph_grounding_per_interaction=(
                1.0 if profile.uses_tenant_graph else 0.0
            ),
            agent_actions_per_interaction=float(len(req.tools_required)),
        )

        axes: dict[str, SeededAxis] = {
            "agent_type":            SeededAxis(value=agent_type.value, rationale_id=rationale_id),
            "channel":               SeededAxis(value=channel.value, rationale_id=rationale_id),
            "build_platform":        SeededAxis(value=profile.build_platform, rationale_id=rationale_id),
            "model_tier":            SeededAxis(value=str(then.get("model_tier") or "economy"),
                                                rationale_id=rationale_id),
            "licensed_user_count":   SeededAxis(value=profile.licensed_user_count,
                                                source="tenant_fact" if tenant_facts else "seed"),
            "unlicensed_user_count": SeededAxis(value=profile.unlicensed_user_count,
                                                source="tenant_fact" if tenant_facts else "seed"),
            "avg_interactions_per_user_per_month": SeededAxis(
                value=profile.avg_interactions_per_user_per_month, source="seed",
            ),
            "uses_tenant_graph":     SeededAxis(value=profile.uses_tenant_graph),
            "uses_dataverse":        SeededAxis(value=profile.uses_dataverse),
            "uses_public_web":       SeededAxis(value=profile.uses_public_web),
        }

        rationale: dict[str, str] = {}
        if rationale_obj:
            rationale = {
                "id": rationale_id or "",
                "source": str(rationale_obj.get("source") or ""),
                "text": str(rationale_obj.get("text") or ""),
            }

        return SeededDesign(
            requirement_id=req.id,
            profile=profile,
            usage=usage,
            axes=axes,
            rationale_id=rationale_id,
            rationale=rationale,
            notes=notes,
            available_channels=available_channels,
        )

    # --------------------------------------------------------------
    def _first_match(self, req: AgentRequirement) -> dict[str, Any]:
        for cell in self.cells:
            when = cell.get("when") or {}
            if self._matches(when, req):
                return cell
        # Fallback to the catch-all (last cell) — should always exist.
        if self.cells:
            return self.cells[-1]
        raise RuntimeError("Decision matrix contains no cells.")

    # --------------------------------------------------------------
    def _available_channels(self, facts: TenantFacts | None) -> list[str]:
        """Return channels the tenant can actually deliver, in matrix order."""
        candidates = list(self.channel_requires_sku.keys())
        if not facts:
            return candidates
        out: list[str] = []
        for channel in candidates:
            required = self.channel_requires_sku.get(channel, "")
            if not required:
                out.append(channel)
                continue
            if facts.has_sku_token(required):
                out.append(channel)
        return out or candidates

    @staticmethod
    def _licensed_seed(req: AgentRequirement, facts: TenantFacts | None) -> int:
        if not facts:
            # Default heuristic: assume audience is licensed for confidential
            # internal scenarios; otherwise none.
            if req.audience == "employees" and req.data_sensitivity in ("confidential", "restricted"):
                return req.audience_size
            return 0
        return min(req.audience_size or facts.copilot_active_users, facts.copilot_active_users)


# ---------------------------------------------------------------------
@dataclass
class TenantFacts:
    """Subset of Part 1 puller outputs the seeder needs.

    Keeping a small, explicit surface here lets us snapshot test the seeder
    without requiring a Repository at hand.
    """

    copilot_assigned_users: int = 0
    copilot_active_users: int = 0
    sku_part_numbers: list[str] = field(default_factory=list)
    sensitivity_labels: list[str] = field(default_factory=list)
    risk_alert_count: int = 0

    def has_sku_token(self, token: str) -> bool:
        token = token.lower()
        return any(token in s.lower() for s in self.sku_part_numbers)

    @classmethod
    def from_repository(cls, repo: Any) -> TenantFacts:
        """Build a TenantFacts from a live Repository (best-effort, no raises)."""
        try:
            pop = repo.latest_licensed_population()
        except Exception:
            pop = []
        try:
            labels = repo.list_sensitivity_labels()
        except Exception:
            labels = []
        try:
            risks = repo.list_risk_signals()
        except Exception:
            risks = []
        return cls(
            copilot_assigned_users=sum(int(p.get("assigned_users") or 0) for p in pop),
            copilot_active_users=sum(int(p.get("active_users_30d") or 0) for p in pop),
            sku_part_numbers=[str(p.get("sku_part_number") or "") for p in pop],
            sensitivity_labels=[str(label.get("sensitivity") or "") for label in labels],
            risk_alert_count=sum(1 for r in risks if str(r.get("severity") or "") == "high"),
        )
