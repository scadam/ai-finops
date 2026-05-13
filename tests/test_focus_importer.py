"""Tests for the FOCUS importer's tagging classification."""
from __future__ import annotations

import io

from ai_finops.ingestion import FocusImporter

CSV_CONTENT = """\
BillingPeriodStart,ChargePeriodStart,BilledCost,EffectiveCost,ServiceName,ServiceCategory,ResourceId,ResourceName,ResourceType,Tags.AgentId,Tags.CostCenter,Tags.Owner,Tags.Environment,UsageQuantity,UsageUnit
2025-01-01,2025-01-15,123.45,120.00,Azure OpenAI,AI,res-1,openai-1,oai,agt-test,FIN-200,owner@example.com,prod,1000,tokens
2025-01-01,2025-01-15,200.00,200.00,Azure AI Search,AI,res-2,search-1,search,agt-test,FIN-200,owner@example.com,prod,1,units
2025-01-01,2025-01-15,87.20,87.20,Azure AI Search,AI,res-orphan,search-orphan,search,,,,,1,units
2025-01-01,2025-01-15,55.55,55.00,Azure SQL Database,Database,res-sql,sqldb,sql,agt-test,FIN-200,owner@example.com,prod,1,GB
"""


def test_split_tagged_separates_required_tags() -> None:
    importer = FocusImporter()
    rows = importer.parse(io.StringIO(CSV_CONTENT))
    tagged, untagged = importer.split_tagged(rows)
    # Azure SQL is not AI-related → excluded from both lists.
    assert len(tagged) == 2
    assert len(untagged) == 1
    assert untagged[0].service_name == "Azure AI Search"

    events = list(importer.to_cost_events(tagged))
    assert all(e["agent_id"] == "agt-test" for e in events)
    services = {e["azure_service"] for e in events}
    assert services == {"azure_openai", "ai_search"}

    untagged_rows = list(importer.to_untagged_rows(untagged))
    assert untagged_rows[0]["missing_tags"] == "AgentId,CostCenter,Owner,Environment"
