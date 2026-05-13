"""What-If scenario comparison + requirement-driven design.

Public surface:

* :class:`ScenarioComparison` — existing combinatorial agent-type comparator.
* :class:`AgentRequirement`   — structured business requirement (Part 2).
* :class:`TechnologySeeder`   — deterministic requirement → seeded design.
* :class:`DecisionEngine`     — pure-function scoring of candidate designs.
"""
from .decision_engine import DecisionEngine, DecisionScore
from .requirement import (
    AgentRequirement,
    RequirementParser,
    parse_free_text,
)
from .scenario_comparison import ScenarioComparison, ScenarioResult
from .seeder import SeededAxis, SeededDesign, TechnologySeeder

__all__ = [
    "AgentRequirement",
    "DecisionEngine",
    "DecisionScore",
    "RequirementParser",
    "ScenarioComparison",
    "ScenarioResult",
    "SeededAxis",
    "SeededDesign",
    "TechnologySeeder",
    "parse_free_text",
]
