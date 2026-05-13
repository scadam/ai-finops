// =====================================================================================
// AI FinOps — single-file Azure deployment (Bicep)
//
// Provisions everything required by copilot-instructions.md §12:
//   * App Service Plan + App Service (FastAPI backend, Linux Python 3.11)
//   * Static Web App (React frontend — placeholder, ready for future build)
//   * Azure SQL Server + Database
//   * Azure Functions App (Linux Python, consumption plan) for ingestion jobs
//   * Azure Service Bus Namespace + queues for async ingestion
//   * Azure Cache for Redis (Basic C0)
//   * Storage Account with FOCUS-exports container
//   * Azure Key Vault with RBAC
//   * Application Insights + Log Analytics workspace
//   * App Configuration store
//   * System-assigned managed identities + RBAC role assignments
//
// Single-click usage: see scripts/deploy.sh.
// =====================================================================================

@description('Short application name used in resource names. Lowercase letters and digits only.')
@minLength(2)
@maxLength(11)
param appName string = 'aifinops'

@description('Environment name (dev / test / prod).')
@allowed([
  'dev'
  'test'
  'prod'
])
param environmentName string = 'dev'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Object ID of the user/service principal that should receive Key Vault admin rights for first-time setup. Leave empty to skip.')
param adminObjectId string = ''

@description('Azure SQL administrator login.')
param sqlAdminLogin string = 'aifinopsadmin'

@description('Azure SQL administrator password.')
@secure()
param sqlAdminPassword string

@description('App Service Plan SKU. Use B1 for dev, P1v3 for prod.')
@allowed([
  'B1'
  'B2'
  'P1v3'
  'P2v3'
])
param appServicePlanSku string = 'B1'

@description('Azure SQL Database SKU.')
@allowed([
  'Basic'
  'S0'
  'S1'
  'S2'
  'S3'
])
param sqlDatabaseSku string = 'S0'

// -------------------------------------------------------------------------------------
// Naming
// -------------------------------------------------------------------------------------
var suffix = uniqueString(resourceGroup().id, environmentName)
var tags = {
  application: appName
  environment: environmentName
  managedBy: 'bicep'
  workload: 'ai-finops'
}

var planName       = 'plan-${appName}-${environmentName}'
var apiName        = 'app-${appName}-api-${environmentName}-${suffix}'
var swaName        = 'swa-${appName}-${environmentName}-${suffix}'
var funcName       = 'func-${appName}-${environmentName}-${suffix}'
var sqlServerName  = 'sql-${appName}-${environmentName}-${suffix}'
var sqlDbName      = 'db-${appName}'
var sbName         = 'sb-${appName}-${environmentName}-${suffix}'
var redisName      = 'redis-${appName}-${environmentName}-${suffix}'
var stgName        = toLower('st${appName}${environmentName}${take(suffix, 8)}')
// Key Vault names are limited to 24 chars; take() guarantees runtime length even though
// Bicep's static analyzer (BCP335) reports a warning for the worst-case input bound.
var kvName         = take('kv${appName}${environmentName}${take(suffix, 8)}', 24)
var laName         = 'log-${appName}-${environmentName}'
var aiName         = 'appi-${appName}-${environmentName}'
var appCfgName     = 'appcs-${appName}-${environmentName}-${suffix}'

// -------------------------------------------------------------------------------------
// Log Analytics + Application Insights
// -------------------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: laName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: aiName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// -------------------------------------------------------------------------------------
// Storage account (FOCUS exports + Functions backing storage + rate-card cache)
// -------------------------------------------------------------------------------------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stgName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource focusContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'focus-exports'
  properties: { publicAccess: 'None' }
}

resource rateCardContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'rate-card-cache'
  properties: { publicAccess: 'None' }
}

// -------------------------------------------------------------------------------------
// Key Vault (RBAC mode)
// -------------------------------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'sql-admin-password'
  properties: {
    value: sqlAdminPassword
    contentType: 'text/plain'
  }
}

// -------------------------------------------------------------------------------------
// App Configuration
// -------------------------------------------------------------------------------------
resource appConfig 'Microsoft.AppConfiguration/configurationStores@2023-03-01' = {
  name: appCfgName
  location: location
  tags: tags
  sku: { name: 'free' }
  properties: {
    disableLocalAuth: false
  }
}

// -------------------------------------------------------------------------------------
// Service Bus
// -------------------------------------------------------------------------------------
resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: sbName
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
}

resource sbQueueIngest 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'ingestion-tasks'
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 5
    enablePartitioning: false
    enableBatchedOperations: true
  }
}

// -------------------------------------------------------------------------------------
// Redis (Basic C0)
// -------------------------------------------------------------------------------------
resource redis 'Microsoft.Cache/Redis@2023-08-01' = {
  name: redisName
  location: location
  tags: tags
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisVersion: '6'
  }
}

// -------------------------------------------------------------------------------------
// Azure SQL
// -------------------------------------------------------------------------------------
resource sqlServer 'Microsoft.Sql/servers@2023-05-01-preview' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlAllowAzure 'Microsoft.Sql/servers/firewallRules@2023-05-01-preview' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-05-01-preview' = {
  parent: sqlServer
  name: sqlDbName
  location: location
  tags: tags
  sku: { name: sqlDatabaseSku, tier: sqlDatabaseSku == 'Basic' ? 'Basic' : 'Standard' }
}

// -------------------------------------------------------------------------------------
// App Service Plan (Linux)
// -------------------------------------------------------------------------------------
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  kind: 'linux'
  sku: { name: appServicePlanSku }
  properties: {
    reserved: true
  }
}

// -------------------------------------------------------------------------------------
// App Service — FastAPI backend
// -------------------------------------------------------------------------------------
var sqlConn = 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:${sqlServer.properties.fullyQualifiedDomainName},1433;Database=${sqlDbName};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryMsi'

resource api 'Microsoft.Web/sites@2023-12-01' = {
  name: apiName
  location: location
  tags: tags
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'gunicorn -w 4 -k uvicorn.workers.UvicornWorker ai_finops.main:app --bind 0.0.0.0:8000'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      alwaysOn: appServicePlanSku != 'B1'
      appSettings: [
        { name: 'AI_FINOPS_ENV',                   value: environmentName }
        { name: 'AI_FINOPS_LOG_LEVEL',             value: 'INFO' }
        { name: 'AI_FINOPS_RATE_CARD_DIR',         value: '/home/site/wwwroot/config/rate_cards' }
        { name: 'AI_FINOPS_DATABASE_URL',          value: sqlConn }
        { name: 'AI_FINOPS_FOCUS_STORAGE_ACCOUNT', value: storage.name }
        { name: 'AI_FINOPS_FOCUS_CONTAINER',       value: 'focus-exports' }
        { name: 'AI_FINOPS_AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
        { name: 'AI_FINOPS_KEY_VAULT_URL',         value: keyVault.properties.vaultUri }
        { name: 'AI_FINOPS_SERVICE_BUS_NAMESPACE', value: '${serviceBus.name}.servicebus.windows.net' }
        { name: 'AI_FINOPS_REDIS_HOST',            value: redis.properties.hostName }
        { name: 'AI_FINOPS_APPCONFIG_ENDPOINT',    value: appConfig.properties.endpoint }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT',  value: 'true' }
        { name: 'ENABLE_ORYX_BUILD',               value: 'true' }
        { name: 'WEBSITES_PORT',                   value: '8000' }
      ]
    }
  }
}

// -------------------------------------------------------------------------------------
// Functions App (ingestion jobs) — Linux consumption plan
// -------------------------------------------------------------------------------------
resource functionsPlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-func-${appName}-${environmentName}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  sku: { name: 'Y1', tier: 'Dynamic' }
  properties: { reserved: true }
}

resource functionsApp 'Microsoft.Web/sites@2023-12-01' = {
  name: funcName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: functionsPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION',      value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME',         value: 'python' }
        { name: 'AI_FINOPS_DATABASE_URL',           value: sqlConn }
        { name: 'AI_FINOPS_FOCUS_STORAGE_ACCOUNT',  value: storage.name }
        { name: 'AI_FINOPS_SERVICE_BUS_NAMESPACE',  value: '${serviceBus.name}.servicebus.windows.net' }
        { name: 'AI_FINOPS_KEY_VAULT_URL',          value: keyVault.properties.vaultUri }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
      ]
    }
  }
}

// -------------------------------------------------------------------------------------
// Static Web App (React frontend placeholder)
// -------------------------------------------------------------------------------------
resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: swaName
  location: 'eastus2'   // SWA only available in select regions
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// -------------------------------------------------------------------------------------
// RBAC role assignments for the App Service + Functions managed identities.
// -------------------------------------------------------------------------------------
// Built-in role definition IDs
var roleStorageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var roleKeyVaultSecretsUser        = '4633458b-17de-408a-b874-0445c86b69e6'
var roleAppConfigDataReader        = '516239f1-63e1-4d78-a4de-a74fb236a071'
var roleServiceBusDataSender       = '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
var roleServiceBusDataReceiver     = '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
var roleCostManagementReader       = '72fafb9e-0641-4937-9268-a91bfd8191a3'
var roleKeyVaultAdministrator      = '00482a5a-887f-4fb3-b363-3b7fe8e74483'
// Read-only RBAC required by the plug-and-play SDK pullers (Part 1).
// Reader is enough for ARM inventory + Defender + Power Platform admin REST.
// Microsoft Graph application permissions (Reports.Read.All, Agent.Read.All,
// Directory.Read.All, SecurityAlert.Read.All, InformationProtectionPolicy.Read.All)
// MUST be granted on the App Registration manually — they are not assignable
// via Bicep. See docs/permissions.md.
var roleReader                     = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

// Backend → Storage
resource raApiStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, api.id, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataContributor)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend → Key Vault
resource raApiKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, api.id, roleKeyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend → App Configuration
resource raApiAppCfg 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appConfig.id, api.id, roleAppConfigDataReader)
  scope: appConfig
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAppConfigDataReader)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend → Service Bus (sender/receiver)
resource raApiSbSend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus.id, api.id, roleServiceBusDataSender)
  scope: serviceBus
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleServiceBusDataSender)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend → Cost Management (subscription scope)
resource raApiCostMgmt 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, api.id, roleCostManagementReader)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCostManagementReader)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend → Reader at resource group scope (Azure inventory puller).
// Customers can elevate to subscription scope manually for full visibility.
resource raApiReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, api.id, roleReader)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleReader)
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Functions → Reader (so the scheduled ingestion fan-out can call ARM).
resource raFuncReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, functionsApp.id, roleReader)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleReader)
    principalId: functionsApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Functions → Cost Management Reader (scheduled FOCUS pulls).
resource raFuncCostMgmt 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, functionsApp.id, roleCostManagementReader)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCostManagementReader)
    principalId: functionsApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Functions → Storage (host + ingestion)
resource raFuncStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionsApp.id, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataContributor)
    principalId: functionsApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Functions → Service Bus receiver
resource raFuncSbReceive 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus.id, functionsApp.id, roleServiceBusDataReceiver)
  scope: serviceBus
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleServiceBusDataReceiver)
    principalId: functionsApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Functions → Key Vault
resource raFuncKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionsApp.id, roleKeyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: functionsApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Optional admin → Key Vault Administrator (for first-time secret seeding from CLI)
resource raAdminKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adminObjectId)) {
  name: guid(keyVault.id, adminObjectId, roleKeyVaultAdministrator)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultAdministrator)
    principalId: adminObjectId
    principalType: 'User'
  }
}

// -------------------------------------------------------------------------------------
// Outputs (consumed by deploy.sh)
// -------------------------------------------------------------------------------------
output apiName string             = api.name
output apiUrl string              = 'https://${api.properties.defaultHostName}'
output functionsName string       = functionsApp.name
output functionsUrl string        = 'https://${functionsApp.properties.defaultHostName}'
output staticWebAppName string    = staticWebApp.name
output staticWebAppUrl string     = 'https://${staticWebApp.properties.defaultHostname}'
output sqlServerFqdn string       = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string     = sqlDb.name
output storageAccountName string  = storage.name
output keyVaultName string        = keyVault.name
output keyVaultUri string         = keyVault.properties.vaultUri
output serviceBusEndpoint string  = '${serviceBus.name}.servicebus.windows.net'
output redisHost string           = redis.properties.hostName
output appInsightsConnString string = appInsights.properties.ConnectionString
output appConfigEndpoint string   = appConfig.properties.endpoint
output resourceGroupName string   = resourceGroup().name
