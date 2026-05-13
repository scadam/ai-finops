"""Centralised OAuth2 scopes and Entra app-role catalogue for every puller.

This is the single source of truth for the App Registration permission list.
``REQUIRED_APP_ROLES`` is consumed by ``docs/permissions.md`` and the
``GET /api/v1/data-sources`` endpoint so operators see exactly which consents
are required to enable a given source.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# OAuth2 scope constants — used with azure.identity credentials.
# ---------------------------------------------------------------------------
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
AZURE_MGMT_SCOPE = "https://management.azure.com/.default"
POWER_PLATFORM_SCOPE = "https://api.bap.microsoft.com/.default"
PURVIEW_SCOPE = "https://purview.azure.net/.default"
DEFENDER_SCOPE = "https://api.securitycenter.microsoft.com/.default"

# ---------------------------------------------------------------------------
# REST API base URLs.
# ---------------------------------------------------------------------------
GRAPH_V1 = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"
AZURE_MGMT = "https://management.azure.com"
POWER_PLATFORM_BAP = "https://api.bap.microsoft.com"
POWER_PLATFORM_PPAI = "https://api.powerplatform.com"


@dataclass(frozen=True)
class AppRole:
    """One entry on the App Registration permission list."""

    api: str          # e.g. "Microsoft Graph"
    name: str         # e.g. "Reports.Read.All"
    role_type: str    # "application" | "delegated" | "azure-rbac"
    granted_for: str  # which puller(s) require it
    notes: str = ""


REQUIRED_APP_ROLES: tuple[AppRole, ...] = (
    # Microsoft Graph (application permissions; admin consent required)
    AppRole("Microsoft Graph", "Reports.Read.All", "application",
            "GraphCreditsPuller, Agent365UsagePuller, GraphLicensePuller",
            "Usage reports for Copilot, Agent 365, Office 365 active users."),
    AppRole("Microsoft Graph", "Directory.Read.All", "application",
            "EntraDirectoryPuller, GraphLicensePuller",
            "subscribedSkus, users, groups, servicePrincipals, appRoleAssignments."),
    AppRole("Microsoft Graph", "Agent.Read.All", "application",
            "Agent365DirectoryPuller",
            "Agent 365 directory (beta /agents endpoint)."),
    AppRole("Microsoft Graph", "AuditLog.Read.All", "application",
            "EntraDirectoryPuller",
            "users.signInActivity for licensed-population sizing."),
    AppRole("Microsoft Graph", "SecurityAlert.Read.All", "application",
            "DefenderPuller",
            "Security alerts attributed to agent service principals."),
    AppRole("Microsoft Graph", "SecurityEvents.Read.All", "application",
            "DefenderPuller",
            "Secure-score endpoint."),
    AppRole("Microsoft Graph", "InformationProtectionPolicy.Read.All", "application",
            "PurviewPuller",
            "Sensitivity label catalogue."),
    AppRole("Microsoft Graph", "Policy.Read.All", "application",
            "PurviewPuller",
            "DLP policies via the Compliance Graph."),
    # Azure RBAC (assigned by Bicep at subscription / RG scope)
    AppRole("Azure", "Reader", "azure-rbac",
            "AzureInventoryPuller",
            "List CognitiveServices, Search, Foundry, ML resources."),
    AppRole("Azure", "Cost Management Reader", "azure-rbac",
            "CostManagementPuller",
            "Query Cost Management FOCUS dataset (replaces CSV uploads)."),
    AppRole("Azure", "Purview Data Reader", "azure-rbac",
            "PurviewPuller",
            "Read sensitivity classifications attached to data sources."),
    # Power Platform Admin REST (delegated to a UAMI granted PP Admin)
    AppRole("Power Platform", "Power Platform Administrator", "azure-rbac",
            "PowerPlatformPuller",
            "List environments, DLP connector groups, capacity add-ons, "
            "Copilot Studio bot inventory and tenant credit pools."),
)


def app_roles_for(source: str) -> list[AppRole]:
    """Return only the roles a given puller needs (substring match)."""
    return [r for r in REQUIRED_APP_ROLES if source in r.granted_for]
