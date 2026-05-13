# Microsoft permissions reference

The plug-and-play data collection layer (Part 1 of the Agent FinOps roadmap)
authenticates with `azure.identity.DefaultAzureCredential` so the same code
path works for managed identity in App Service / Functions, federated
workload identity in CI, and `az login` device-code locally.

Each puller is **disabled by default** via the `AI_FINOPS_INGEST_*_ENABLED`
flags in `.env.example`. Enable a source only after granting the matching
role / app role.

## Quick reference — minimum read-only permissions

| Source                 | Where granted                       | Permission                                                                 |
| ---------------------- | ----------------------------------- | -------------------------------------------------------------------------- |
| Agent 365 directory    | App Registration (Microsoft Graph)  | `Agent.Read.All` (beta)                                                    |
| Agent 365 usage report | App Registration (Microsoft Graph)  | `Reports.Read.All`                                                         |
| Entra ID directory     | App Registration (Microsoft Graph)  | `Directory.Read.All`, `User.Read.All`, `AuditLog.Read.All`                |
| Entra licensing        | App Registration (Microsoft Graph)  | `Organization.Read.All`                                                    |
| Purview                | App Registration (Microsoft Graph + Purview Data Plane) | `InformationProtectionPolicy.Read.All`, `Purview Data Reader` |
| Defender for Cloud     | Subscription RBAC                   | `Security Reader` **and** Microsoft Graph `SecurityAlert.Read.All`        |
| Power Platform admin   | Tenant role                         | `Power Platform Administrator` (read APIs)                                 |
| Azure resources        | Subscription RBAC                   | `Reader`                                                                   |
| Azure cost             | Subscription RBAC                   | `Cost Management Reader`                                                   |

## Bicep coverage

`infra/main.bicep` automatically assigns the **subscription-scope Azure RBAC**
roles to both managed identities (`api` + `functionsApp`):

* `Reader` — for `azure-mgmt-resource`, `azure-mgmt-cognitiveservices`,
  `azure-mgmt-search`, `azure-mgmt-machinelearningservices`, and
  `azure-mgmt-monitor` calls used by the Azure inventory puller.
* `Cost Management Reader` — for the Cost Management FOCUS pull.

Microsoft Graph application permissions and Power Platform tenant roles
**must be granted manually** on the App Registration after deploy — they are
not assignable via Bicep. See the table above for the exact list, then run:

```bash
az ad app permission admin-consent --id <APP_OBJECT_ID>
```

## Per-source feature flags

`.env.example` ships every source set to `false`. Flip the matching flag to
`true` only after the permission above is granted:

```env
AI_FINOPS_INGEST_AGENT365_ENABLED=true
AI_FINOPS_INGEST_ENTRA_DIRECTORY_ENABLED=true
AI_FINOPS_INGEST_PURVIEW_ENABLED=true
# ...etc
```

The Governance tab's *Data Sources* panel (powered by `GET /api/v1/data-sources`)
shows which sources are enabled, the last-success time, and the SDK call
each puller uses — so a missing permission surfaces as a per-source error
rather than a silent gap in your cost data.

## Triggering a run

```bash
# Plan mode — shows what would run without contacting any SDK
curl -X POST https://<host>/api/v1/ingestion/run -d '{}' -H 'content-type: application/json'

# Targeted execute — only the Agent365 + cost management pullers
curl -X POST https://<host>/api/v1/ingestion/run \
     -H 'content-type: application/json' \
     -d '{"jobs": ["agent365", "cost_management"]}'
```

## Lineage and trust

Every persisted row carries `source_system` + `raw_record_id`. The
`Repository.insert_*` paths reject any row missing these fields, eliminating
"unknown-source" inserts. The audit table `IngestionRun` records every
fan-out for forensic review (visible at `GET /api/v1/ingestion/runs`).
