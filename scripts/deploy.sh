#!/usr/bin/env bash
# =====================================================================================
# AI FinOps — single-click Azure deployment
# -------------------------------------------------------------------------------------
# This script provisions every Azure resource required by copilot-instructions.md §12
# and deploys the Python FastAPI backend + Functions ingestion app.
#
# Prerequisites:
#   * Azure CLI 2.55+ (run `az login` first; or `az login --use-device-code`)
#   * Bash 4+, zip, python 3.11+
#   * Owner / Contributor + User Access Administrator on the target subscription
#
# Usage:
#   ./scripts/deploy.sh                                         # interactive defaults
#   APP_NAME=mycorpfin LOCATION=westeurope ENV_NAME=prod \
#       SQL_ADMIN_PASSWORD='S3cret!' ./scripts/deploy.sh         # non-interactive
#
# Idempotent — safe to re-run; Bicep deployments are incremental by default.
# =====================================================================================

set -euo pipefail

# ------------------------------------------------------------------ Config / defaults
APP_NAME="${APP_NAME:-aifinops}"
ENV_NAME="${ENV_NAME:-dev}"
LOCATION="${LOCATION:-eastus}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-${APP_NAME}-${ENV_NAME}}"
APP_PLAN_SKU="${APP_PLAN_SKU:-B1}"
SQL_DB_SKU="${SQL_DB_SKU:-S0}"
SQL_ADMIN_LOGIN="${SQL_ADMIN_LOGIN:-aifinopsadmin}"
SQL_ADMIN_PASSWORD="${SQL_ADMIN_PASSWORD:-}"
DEPLOYMENT_NAME="ai-finops-$(date -u +%Y%m%dT%H%M%S)"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-}"

# Derive paths relative to this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFRA_DIR="${REPO_ROOT}/infra"
BUILD_DIR="${REPO_ROOT}/.build"

# ------------------------------------------------------------------ UI helpers
log()    { printf '\e[1;34m[deploy]\e[0m %s\n' "$*"; }
ok()     { printf '\e[1;32m[ ok  ]\e[0m %s\n' "$*"; }
warn()   { printf '\e[1;33m[warn ]\e[0m %s\n' "$*"; }
err()    { printf '\e[1;31m[fail ]\e[0m %s\n' "$*" >&2; }
fatal()  { err "$*"; exit 1; }

# ------------------------------------------------------------------ Pre-flight
log "Pre-flight checks ..."
command -v az >/dev/null 2>&1 || fatal "Azure CLI 'az' not found. Install: https://aka.ms/azcli"
command -v zip >/dev/null 2>&1 || fatal "'zip' is required."
command -v python3 >/dev/null 2>&1 || fatal "'python3' is required."

if ! az account show >/dev/null 2>&1; then
  warn "Not logged in to Azure. Running 'az login' ..."
  az login --only-show-errors >/dev/null
fi

if [[ -n "${SUBSCRIPTION_ID}" ]]; then
  log "Setting active subscription to ${SUBSCRIPTION_ID}"
  az account set --subscription "${SUBSCRIPTION_ID}"
fi
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
SIGNED_IN_USER_OID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || echo "")

ok "Subscription : ${SUBSCRIPTION_ID}"
ok "Tenant       : ${TENANT_ID}"
ok "Signed-in OID: ${SIGNED_IN_USER_OID:-<service principal — skipping KV admin grant>}"

# Generate a strong SQL password if the caller didn't provide one.
if [[ -z "${SQL_ADMIN_PASSWORD}" ]]; then
  SQL_ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
print("Aifn1!" + ''.join(secrets.choice(alphabet) for _ in range(20)))
PY
  )"
  warn "Generated SQL admin password (saved to Key Vault as 'sql-admin-password')."
fi

# ------------------------------------------------------------------ Resource group
log "Ensuring resource group '${RESOURCE_GROUP}' in '${LOCATION}' ..."
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" \
  --tags application="${APP_NAME}" environment="${ENV_NAME}" managedBy=deploy.sh \
  --only-show-errors >/dev/null
ok "Resource group ready."

# ------------------------------------------------------------------ Bicep deployment
log "Validating Bicep template ..."
az deployment group validate \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${INFRA_DIR}/main.bicep" \
  --parameters \
      appName="${APP_NAME}" \
      environmentName="${ENV_NAME}" \
      location="${LOCATION}" \
      appServicePlanSku="${APP_PLAN_SKU}" \
      sqlDatabaseSku="${SQL_DB_SKU}" \
      sqlAdminLogin="${SQL_ADMIN_LOGIN}" \
      sqlAdminPassword="${SQL_ADMIN_PASSWORD}" \
      adminObjectId="${SIGNED_IN_USER_OID}" \
  --only-show-errors >/dev/null
ok "Template validated."

log "Provisioning resources (this can take 5-10 minutes) ..."
DEPLOY_OUTPUTS_JSON=$(az deployment group create \
  --name "${DEPLOYMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${INFRA_DIR}/main.bicep" \
  --parameters \
      appName="${APP_NAME}" \
      environmentName="${ENV_NAME}" \
      location="${LOCATION}" \
      appServicePlanSku="${APP_PLAN_SKU}" \
      sqlDatabaseSku="${SQL_DB_SKU}" \
      sqlAdminLogin="${SQL_ADMIN_LOGIN}" \
      sqlAdminPassword="${SQL_ADMIN_PASSWORD}" \
      adminObjectId="${SIGNED_IN_USER_OID}" \
  --query properties.outputs \
  --output json)

API_NAME=$(echo "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["apiName"]["value"])')
API_URL=$(echo  "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["apiUrl"]["value"])')
FUNC_NAME=$(echo "${DEPLOY_OUTPUTS_JSON}"       | python3 -c 'import sys,json;print(json.load(sys.stdin)["functionsName"]["value"])')
SWA_NAME=$(echo "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["staticWebAppName"]["value"])')
SWA_URL=$(echo  "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["staticWebAppUrl"]["value"])')
KV_NAME=$(echo  "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["keyVaultName"]["value"])')
SQL_FQDN=$(echo "${DEPLOY_OUTPUTS_JSON}"        | python3 -c 'import sys,json;print(json.load(sys.stdin)["sqlServerFqdn"]["value"])')

ok "Provisioning complete."
ok "API name           : ${API_NAME}"
ok "API URL            : ${API_URL}"
ok "Functions app      : ${FUNC_NAME}"
ok "Static Web App     : ${SWA_NAME}  (${SWA_URL})"
ok "Key Vault          : ${KV_NAME}"
ok "SQL Server FQDN    : ${SQL_FQDN}"

# ------------------------------------------------------------------ Build & deploy backend
log "Building Python deployment package ..."
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/app"
# Copy backend source + config (rate cards must ship with the app)
cp -r "${REPO_ROOT}/src/ai_finops"        "${BUILD_DIR}/app/"
cp -r "${REPO_ROOT}/config"               "${BUILD_DIR}/app/"
cp    "${REPO_ROOT}/requirements.txt"     "${BUILD_DIR}/app/"

ZIP_PATH="${BUILD_DIR}/api.zip"
( cd "${BUILD_DIR}/app" && zip -qr "${ZIP_PATH}" . )
ok "Package built : ${ZIP_PATH} ($(du -h "${ZIP_PATH}" | cut -f1))"

log "Deploying backend to App Service '${API_NAME}' (Oryx will install requirements) ..."
az webapp deploy \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${API_NAME}" \
  --src-path "${ZIP_PATH}" \
  --type zip \
  --async false \
  --only-show-errors >/dev/null
ok "Backend deployed."

# Restart so Oryx picks up the new build deterministically
az webapp restart --resource-group "${RESOURCE_GROUP}" --name "${API_NAME}" --only-show-errors >/dev/null
ok "App Service restarted."

# ------------------------------------------------------------------ Smoke test
log "Waiting for backend warm-up (max 90s) ..."
for i in $(seq 1 18); do
  if curl -fsS --max-time 5 "${API_URL}/api/v1/health" >/dev/null 2>&1; then
    ok "Backend healthy at ${API_URL}/api/v1/health"
    break
  fi
  sleep 5
  if [[ $i -eq 18 ]]; then
    warn "Backend did not respond within 90s; check logs with:"
    warn "    az webapp log tail --resource-group ${RESOURCE_GROUP} --name ${API_NAME}"
  fi
done

# ------------------------------------------------------------------ Summary
cat <<EOF

──────────────────────────────────────────────────────────────────────────────
  AI FinOps deployment complete 🎉
──────────────────────────────────────────────────────────────────────────────
  Backend API       : ${API_URL}
  API docs (Swagger): ${API_URL}/docs
  Health check      : ${API_URL}/api/v1/health
  Static Web App    : ${SWA_URL}    (frontend not yet built — see README)
  Functions app     : https://${FUNC_NAME}.azurewebsites.net   (no functions deployed yet)
  Resource group    : ${RESOURCE_GROUP}
  Subscription      : ${SUBSCRIPTION_ID}
──────────────────────────────────────────────────────────────────────────────

Next steps:
  1. Wire ingestion jobs (Microsoft Graph, Cost Management FOCUS export).
  2. Build & deploy the React frontend to the Static Web App.
  3. Schedule the Bicep redeploy in CI/CD for environment parity.
EOF
