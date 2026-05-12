# AI FinOps

Enterprise FinOps for the **Microsoft AI Frontier Platform** —
M365 Copilot per-seat licenses, Copilot Studio Credits, and Azure OpenAI / Foundry
consumption — built per [`copilot-instructions.md`](./copilot-instructions.md).

This repo contains:

* A **Python 3.11 / FastAPI** backend that implements the three-meter cost model
  (per-seat • Copilot Credits • Azure consumption), the What-If cost modeller,
  the optimisation recommender and the rate-card service.
* A **single-click Azure deployment** (`scripts/deploy.sh` + `infra/main.bicep`)
  that provisions every resource listed in the spec §12.
* A complete set of **YAML rate cards** under [`config/rate_cards/`](./config/rate_cards),
  hot-reloaded by the backend with a 7-day staleness alert.
* **Regression tests** that document the canonical billing rules from Microsoft Learn
  worked examples (spec §10.1).

> The React UI (spec §8) and live ingestion connectors (spec §6.1) are scoped as
> follow-on work — see [Roadmap](#roadmap). The backend, modeller, optimiser and
> deployment story are fully implemented and shippable today.

---

## Architecture

```
                            ┌─────────────────────────┐
   Microsoft Graph API ───▶│  Azure Functions (Python)│──┐
   Azure Cost Mgmt FOCUS ──▶│   ingestion jobs (TODO) │  │
   Agent 365 registry  ───▶ └──────────┬──────────────┘  │   ┌──────────────┐
                                       │ Service Bus      ├──▶│  Azure SQL    │
                            ┌──────────▼──────────────┐  │   │  Cost Ledger  │
                            │  FastAPI backend         │──┤   └──────────────┘
   React SPA (TODO)  ──────▶│  ai_finops.main:app      │  │   ┌──────────────┐
                            │  • RateCardService       │  ├──▶│  Redis Cache │
                            │  • CostCalculator        │  │   └──────────────┘
                            │  • ScenarioComparison    │  │   ┌──────────────┐
                            │  • OptimisationRecomm.   │  └──▶│ Storage / KV │
                            │  • REST API (§7)         │      │ FOCUS export│
                            └──────────────────────────┘      └──────────────┘
                                       │
                                       └──▶ Application Insights + Log Analytics
```

---

## Repository layout

```
.
├── copilot-instructions.md         # Full enterprise spec (1568 lines)
├── README.md                       # This file
├── pyproject.toml / requirements.txt
├── .env.example
├── config/
│   ├── rate_cards/                 # Six YAML rate cards (per_seat, credits, OpenAI, Foundry, AI Search, infra)
│   └── allocation/split_rules.yaml
├── src/ai_finops/
│   ├── main.py                     # FastAPI app factory
│   ├── config.py                   # pydantic-settings
│   ├── api/                        # routes + schemas
│   ├── domain/                     # enums + dataclasses (CostEvent, AgentProfile, ...)
│   ├── services/
│   │   ├── rate_card_service.py    # hot-reloads YAML, 7-day staleness flag
│   │   └── cost_calculator.py      # the three-meter algorithm
│   ├── modeler/scenario_comparison.py
│   ├── optimisation/recommender.py # 11 ranked savings rules
│   └── ingestion/                  # connector stubs (Graph, Cost Mgmt, Agent 365)
├── tests/                          # pytest — regression fixtures from spec §10.1
├── infra/main.bicep                # Single-file Bicep IaC for spec §12 stack
├── infra/main.parameters.json
└── scripts/deploy.sh               # Single-click Azure deploy
```

---

## Local development

### Prerequisites

* Python **3.11+**
* (Optional) Azure CLI 2.55+ if you want to deploy

### Install + run

```bash
python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Start the API
uvicorn ai_finops.main:app --reload
# → Swagger UI: http://localhost:8000/docs
# → Health    : http://localhost:8000/api/v1/health
```

### Tests + lint

```bash
pytest                          # 15 tests — regression fixtures + API smoke
ruff check src tests            # lint
mypy src                        # optional type-check
```

### Try the What-If modeller from curl

```bash
curl -X POST http://localhost:8000/api/v1/scenarios/compare \
  -H 'Content-Type: application/json' \
  -d '{
        "base_profile": {
          "agent_name": "Helpdesk",
          "channel": "m365_copilot",
          "licensed_user_count": 500,
          "unlicensed_user_count": 100,
          "avg_interactions_per_user_per_month": 50,
          "primary_model_id": "gpt_4o_mini",
          "avg_tokens_input_per_interaction": 1500,
          "avg_tokens_output_per_interaction": 400
        },
        "usage": { "generative_answers_per_interaction": 1,
                   "tenant_graph_grounding_per_interaction": 1 },
        "period_months": 1
      }' | python -m json.tool
```

---

## Single-click Azure deployment

`scripts/deploy.sh` is the one entry point. It will:

1. Validate `az` is installed and you are logged in.
2. Create the resource group `rg-<APP_NAME>-<ENV_NAME>`.
3. Validate + deploy [`infra/main.bicep`](./infra/main.bicep), provisioning:
   * App Service Plan (Linux) + App Service (FastAPI, Python 3.11)
   * Static Web App (React frontend placeholder)
   * Azure SQL Server + Database (with AAD-MSI connection string for the API)
   * Azure Functions App (Linux Python, consumption plan) for ingestion
   * Service Bus namespace + `ingestion-tasks` queue
   * Azure Cache for Redis (Basic C0)
   * Storage account + `focus-exports` and `rate-card-cache` blob containers
   * Key Vault (RBAC mode) — SQL admin password stored as a secret
   * App Configuration store
   * Application Insights + Log Analytics workspace
   * **System-assigned managed identities** on the App Service and Functions, with
     RBAC role assignments for Storage, Key Vault, App Config, Service Bus, and
     Cost Management Reader on the resource group.
4. Build a deployment zip including the backend source + rate cards.
5. `az webapp deploy` the package to the App Service (Oryx installs `requirements.txt`).
6. Restart the API and run a `/api/v1/health` smoke test.

### Run it

```bash
# Recommended: log in first, set your subscription
az login
az account set --subscription "<subscription-id>"

# Then a single command:
./scripts/deploy.sh
```

Configuration via environment variables:

| Var                    | Default                             | Notes |
|------------------------|-------------------------------------|-------|
| `APP_NAME`             | `aifinops`                          | ≤11 chars, lowercase + digits |
| `ENV_NAME`             | `dev`                               | `dev` / `test` / `prod` |
| `LOCATION`             | `eastus`                            | Any Azure region |
| `RESOURCE_GROUP`       | `rg-${APP_NAME}-${ENV_NAME}`        | Created if missing |
| `APP_PLAN_SKU`         | `B1`                                | `B1`, `B2`, `P1v3`, `P2v3` |
| `SQL_DB_SKU`           | `S0`                                | `Basic`, `S0`, `S1`, `S2`, `S3` |
| `SQL_ADMIN_LOGIN`      | `aifinopsadmin`                     | |
| `SQL_ADMIN_PASSWORD`   | *auto-generated*                    | Saved to Key Vault as `sql-admin-password` |
| `SUBSCRIPTION_ID`      | (current `az` context)              | |

Example for production:

```bash
APP_NAME=mycorpfin ENV_NAME=prod LOCATION=westeurope \
  APP_PLAN_SKU=P1v3 SQL_DB_SKU=S3 \
  SQL_ADMIN_PASSWORD='Str0ng-P@ssw0rd!' ./scripts/deploy.sh
```

### Re-deploys

The script is **idempotent** — Bicep deployments are incremental, and re-running
just pushes a new code zip. To deploy only application code without re-running
Bicep:

```bash
APP_NAME=aifinops ENV_NAME=dev ./scripts/deploy.sh    # safe — no destructive changes
```

### Required permissions

The principal running `deploy.sh` needs:

* **Contributor** on the subscription (or target resource group).
* **User Access Administrator** to create the role assignments.
* **Application Administrator** in Entra (only if you create the API app
  registration — not required for the bare backend deploy).

### Cleanup

```bash
az group delete --name rg-aifinops-dev --yes --no-wait
```

---

## API surface

All endpoints are under `/api/v1` and documented at `/docs`. The currently
implemented routes (functional or scaffolded) are listed in `copilot-instructions.md` §7.
Highlights:

| Method | Path                                  | Purpose |
|--------|---------------------------------------|---------|
| GET    | `/api/v1/health`                      | Service health + rate-card freshness |
| GET    | `/api/v1/rate-cards`                  | Current rate card YAML payloads |
| GET    | `/api/v1/rate-cards/refresh-status`   | Loaded-at + staleness for each card |
| POST   | `/api/v1/rate-cards/reload`           | Force rate card hot-reload |
| POST   | `/api/v1/agents/{id}/estimate`        | What-If estimate for one agent |
| POST   | `/api/v1/scenarios/compare`           | Side-by-side comparison across agent technologies |
| GET    | `/api/v1/optimisations`               | Ranked savings recommendations (stub until DB wired) |
| GET    | `/api/v1/cost/{ledger,summary,trends}`| Cost ledger reads (stubs until DB wired) |
| GET    | `/api/v1/reports/executive-summary`   | Monthly executive summary (stub) |
| GET    | `/api/v1/reports/focus-export`        | FOCUS 1.1 export (stub) |

---

## Key design rules

These come straight from the spec and are encoded in code + tests:

1. **Three meters, never collapsed.** Per-seat, Copilot Credits, and Azure
   consumption are always reported separately. Hybrid Studio + Foundry agents
   bill on **both** Credits and Azure tokens — they are summed, never chosen
   between (see `tests/test_cost_calculator.py::test_hybrid_studio_foundry_both_meters_fire`).
2. **B2E zero-rating.** When an M365-Copilot-licensed user accesses a Copilot
   Studio agent on the M365 channel, credit cost is **$0** but **shadow credits**
   are still recorded for utilisation reporting.
3. **Declarative free tier.** Instruction-only / public-web declarative agents
   are **free for all users** (licensed and unlicensed).
4. **No hardcoded prices.** Every dollar value lives in `config/rate_cards/*.yaml`.
   The `RateCardService` flags any card whose `effective_date` is older than
   7 days.
5. **Decimal everywhere** — currency math never uses `float`.
6. **Pack-vs-PAYG with overflow.** When credits exceed 25 000/month, the
   calculator uses `floor(packs)` plus PAYG overflow, ensuring the agent never
   stops on pack exhaustion.
7. **Forward-looking pricing flagged.** Frontier preview (E7, GPT-5.4 Pro) is
   marked `confidence=low` in every breakdown.

See `copilot-instructions.md` §13 for the full guard-rail list.

---

## Roadmap

The areas marked **TODO** in `src/ai_finops/ingestion/` and the React UI
(spec §8) are out of scope for the initial deployment and are documented as
follow-on work:

* `src/ai_finops/ingestion/credits_puller.py` — Microsoft Graph Reports.Read.All
* `src/ai_finops/ingestion/focus_loader.py` — Azure Cost Management FOCUS export
* `src/ai_finops/ingestion/license_resolver.py` — User license / sign-in activity
* `src/ai_finops/ingestion/agent_registry_puller.py` — Agent 365 registry
* React SPA (Dashboard / Agent Explorer / What-If / Optimisations / Governance)
* Power BI semantic model + FOCUS 1.1 export to ADLS

The Bicep template already provisions every Azure resource these features will
need (Storage, Service Bus, Functions, Static Web App, App Configuration, Key
Vault), so each feature can ship as a self-contained PR.

---

## License

MIT — see `copilot-instructions.md` for spec attribution to Microsoft Learn.

