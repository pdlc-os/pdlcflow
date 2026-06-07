# pdlcflow on Azure — full-parity port of the CDK stacks.
# Container Apps (api + worker), Postgres Flexible Server, Azure Cache for Redis,
# Storage (artifacts/events/studio static site) + CDN, Azure OpenAI, Event Hubs,
# Key Vault, AD B2C, Log Analytics.

locals {
  name = var.project_name
  tags = merge({ app = "pdlcflow", managed_by = "terraform" }, var.tags)
  env = merge({
    PDLC_TASK_STORE                = "postgres"
    PDLC_ANALYTICS_BACKEND         = "postgres"
    PDLC_CLICKSTREAM_SINK          = "postgres"
    PDLC_USE_POSTGRES_CHECKPOINTER = "true"
    PDLC_USE_REDIS_BUS             = "true"
    PDLC_ARTIFACT_STORE            = "s3"
    PDLC_DEFAULT_LLM_PROVIDER      = "azure"
    PDLC_WIRE_LLM                  = "true"
  }, var.app_env)
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = "${local.name}-rg"
  location = var.location
  tags     = local.tags
}

# ───────────────────────── network ─────────────────────────
resource "azurerm_virtual_network" "vnet" {
  name                = "${local.name}-vnet"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.10.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "apps" {
  name                 = "apps"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.10.0.0/21"]
}

resource "azurerm_subnet" "db" {
  name                 = "db"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.10.8.0/24"]
  delegation {
    name = "fs"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# ───────────────────────── data: Postgres + Redis ─────────────────────────
resource "azurerm_private_dns_zone" "pg" {
  name                = "${local.name}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  name                  = "${local.name}-pg-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.pg.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
}

resource "azurerm_postgresql_flexible_server" "pg" {
  name                          = "${local.name}-pg"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  administrator_login           = var.db_username
  administrator_password        = var.db_password
  sku_name                      = var.db_sku
  storage_mb                    = 32768
  delegated_subnet_id           = azurerm_subnet.db.id
  private_dns_zone_id           = azurerm_private_dns_zone.pg.id
  public_network_access_enabled = false
  zone                          = "1"
  depends_on                    = [azurerm_private_dns_zone_virtual_network_link.pg]
  tags                          = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "db" {
  name      = var.db_name
  server_id = azurerm_postgresql_flexible_server.pg.id
}

resource "azurerm_redis_cache" "redis" {
  name                = "${local.name}-redis"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  tags                = local.tags
}

# ───────────────────────── object storage + static Studio site ─────────────────────────
resource "azurerm_storage_account" "main" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  static_website {
    index_document     = "index.html"
    error_404_document = "index.html"
  }
  tags = local.tags
}

resource "azurerm_storage_container" "artifacts" {
  name                  = "artifacts"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "events" {
  name                  = "events"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# ───────────────────────── edge: CDN for the Studio static site ─────────────────────────
resource "azurerm_cdn_profile" "studio" {
  name                = "${local.name}-cdn"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard_Microsoft"
  tags                = local.tags
}

resource "azurerm_cdn_endpoint" "studio" {
  name                = "${local.name}-studio"
  profile_name        = azurerm_cdn_profile.studio.name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  origin_host_header  = azurerm_storage_account.main.primary_web_host
  origin {
    name      = "studio"
    host_name = azurerm_storage_account.main.primary_web_host
  }
  tags = local.tags
}

# ───────────────────────── secrets: Key Vault ─────────────────────────
resource "azurerm_key_vault" "main" {
  name                = "${local.name}-kv"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  tags                = local.tags
}

resource "azurerm_key_vault_secret" "db_url" {
  name         = "pdlc-db-url"
  key_vault_id = azurerm_key_vault.main.id
  value        = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${azurerm_postgresql_flexible_server.pg.fqdn}:5432/${var.db_name}"
}

# ───────────────────────── LLM: Azure OpenAI ─────────────────────────
resource "azurerm_cognitive_account" "openai" {
  name                = "${local.name}-openai"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = local.tags
}

resource "azurerm_cognitive_deployment" "frontier" {
  name                 = "premium"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06"
  }
  scale {
    type = "Standard"
  }
}

# ───────────────────────── events: Event Hubs ─────────────────────────
resource "azurerm_eventhub_namespace" "events" {
  name                = "${local.name}-eh"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_eventhub" "events" {
  name                = "clickstream"
  namespace_name      = azurerm_eventhub_namespace.events.name
  resource_group_name = azurerm_resource_group.main.name
  partition_count     = 2
  message_retention   = 7
}

# ───────────────────────── auth: Azure AD B2C ─────────────────────────
resource "azurerm_aadb2c_directory" "auth" {
  resource_group_name     = azurerm_resource_group.main.name
  display_name            = "pdlcflow"
  domain_name             = "${local.name}b2c.onmicrosoft.com"
  country_code            = "US"
  data_residency_location = "United States"
  sku_name                = "PremiumP1"
}

# ───────────────────────── compute: Container Apps (api + worker) ─────────────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${local.name}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id   = azurerm_subnet.apps.id
  tags                       = local.tags
}

resource "azurerm_container_app" "api" {
  name                         = "${local.name}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  secret {
    name  = "db-url"
    value = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${azurerm_postgresql_flexible_server.pg.fqdn}:5432/${var.db_name}"
  }

  template {
    container {
      name   = "api"
      image  = var.api_image
      cpu    = var.api_cpu
      memory = var.api_memory

      env {
        name        = "PDLC_DB_URL"
        secret_name = "db-url"
      }
      env {
        name  = "PDLC_REDIS_URL"
        value = "rediss://${azurerm_redis_cache.redis.hostname}:6380/0"
      }
      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}

resource "azurerm_container_app" "worker" {
  name                         = "${local.name}-worker"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  secret {
    name  = "db-url"
    value = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${azurerm_postgresql_flexible_server.pg.fqdn}:5432/${var.db_name}"
  }

  template {
    container {
      name    = "worker"
      image   = var.api_image
      cpu     = var.api_cpu
      memory  = var.api_memory
      command = ["uv", "run", "arq", "app.worker.arq_settings.WorkerSettings"]

      env {
        name        = "PDLC_DB_URL"
        secret_name = "db-url"
      }
      env {
        name  = "PDLC_REDIS_URL"
        value = "rediss://${azurerm_redis_cache.redis.hostname}:6380/0"
      }
      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}
