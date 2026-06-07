# pdlcflow on GCP — full-parity port of the CDK stacks.
# Cloud Run (api + worker), Cloud SQL Postgres, Memorystore Redis, GCS
# (artifacts/events/studio), Cloud CDN for the Studio, Identity Platform,
# Pub/Sub + BigQuery (clickstream), Vertex AI access, Secret Manager.

locals {
  name   = var.project_name
  labels = merge({ app = "pdlcflow", managed_by = "terraform" }, var.labels)
  env = merge({
    PDLC_TASK_STORE                = "postgres"
    PDLC_ANALYTICS_BACKEND         = "postgres"
    PDLC_CLICKSTREAM_SINK          = "postgres"
    PDLC_USE_POSTGRES_CHECKPOINTER = "true"
    PDLC_USE_REDIS_BUS             = "true"
    PDLC_ARTIFACT_STORE            = "s3"
    PDLC_DEFAULT_LLM_PROVIDER      = "vertex"
    PDLC_WIRE_LLM                  = "true"
  }, var.app_env)
}

# ───────────────────────── network ─────────────────────────
resource "google_compute_network" "vpc" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${local.name}-subnet"
  ip_cidr_range = "10.8.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# Private services access so Cloud SQL / Memorystore get private IPs.
resource "google_compute_global_address" "private_range" {
  name          = "${local.name}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_range.name]
}

# Serverless VPC connector so Cloud Run reaches the private DB/Redis.
resource "google_vpc_access_connector" "connector" {
  name          = "${local.name}-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.9.0.0/28"
}

# ───────────────────────── data: Cloud SQL + Memorystore ─────────────────────────
resource "google_sql_database_instance" "postgres" {
  name                = "${local.name}-pg"
  database_version    = "POSTGRES_17"
  region              = var.region
  deletion_protection = false
  depends_on          = [google_service_networking_connection.psa]
  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL"
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }
}

resource "google_sql_database" "db" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "user" {
  name     = var.db_username
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

resource "google_redis_instance" "redis" {
  name               = "${local.name}-redis"
  tier               = "STANDARD_HA"
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  redis_version      = "REDIS_7_0"
}

# ───────────────────────── object storage ─────────────────────────
resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-${local.name}-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  versioning {
    enabled = true
  }
  labels = local.labels
}

resource "google_storage_bucket" "events" {
  name                        = "${var.project_id}-${local.name}-events"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = local.labels
}

resource "google_storage_bucket" "studio" {
  name                        = "${var.project_id}-${local.name}-studio"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }
  labels = local.labels
}

# ───────────────────────── secrets ─────────────────────────
resource "google_secret_manager_secret" "db_url" {
  secret_id = "${local.name}-db-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${google_sql_database_instance.postgres.private_ip_address}:5432/${var.db_name}"
}

# ───────────────────────── LLM: Vertex AI service account ─────────────────────────
resource "google_service_account" "runtime" {
  account_id   = "${local.name}-runtime"
  display_name = "pdlcflow Cloud Run runtime"
}

resource "google_project_iam_member" "vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# ───────────────────────── compute: Cloud Run (api + worker) ─────────────────────────
resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.runtime.email
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.api_image
      ports {
        container_port = 8000
      }
      resources {
        limits = {
          cpu    = var.api_cpu
          memory = var.api_memory
        }
      }
      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "PDLC_DB_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "PDLC_REDIS_URL"
        value = "redis://${google_redis_instance.redis.host}:6379/0"
      }
      env {
        name  = "PDLC_S3_ARTIFACTS_BUCKET"
        value = google_storage_bucket.artifacts.name
      }
    }
  }
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "${local.name}-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  template {
    service_account = google_service_account.runtime.email
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    scaling {
      min_instance_count = 1
    }
    containers {
      image   = var.api_image
      command = ["uv", "run", "arq", "app.worker.arq_settings.WorkerSettings"]
      resources {
        limits = {
          cpu    = var.api_cpu
          memory = var.api_memory
        }
      }
      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name  = "PDLC_REDIS_URL"
        value = "redis://${google_redis_instance.redis.host}:6379/0"
      }
    }
  }
}

# Public, unauthenticated access to the API service (auth is enforced in-app).
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ───────────────────────── edge: Cloud CDN for the Studio ─────────────────────────
resource "google_compute_backend_bucket" "studio" {
  name        = "${local.name}-studio-bb"
  bucket_name = google_storage_bucket.studio.name
  enable_cdn  = true
}

resource "google_compute_url_map" "studio" {
  name            = "${local.name}-studio-url"
  default_service = google_compute_backend_bucket.studio.id
}

resource "google_compute_target_http_proxy" "studio" {
  name    = "${local.name}-studio-proxy"
  url_map = google_compute_url_map.studio.id
}

resource "google_compute_global_forwarding_rule" "studio" {
  name       = "${local.name}-studio-fr"
  target     = google_compute_target_http_proxy.studio.id
  port_range = "80"
}

# ───────────────────────── auth: Identity Platform ─────────────────────────
resource "google_identity_platform_config" "auth" {
  project = var.project_id
}

# ───────────────────────── events: Pub/Sub + BigQuery ─────────────────────────
resource "google_pubsub_topic" "events" {
  name   = "${local.name}-events"
  labels = local.labels
}

resource "google_bigquery_dataset" "events" {
  dataset_id    = "${replace(local.name, "-", "_")}_events"
  location      = var.region
  labels        = local.labels
  friendly_name = "pdlcflow clickstream"
}
