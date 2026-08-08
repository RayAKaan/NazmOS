# NazmOS production infrastructure on Google Cloud (KSA region me-central2).
#
# Resources:
#   - VPC + Serverless VPC connector
#   - Cloud SQL PostgreSQL (multi-zone backups)
#   - Memorystore Redis (Standard HA)
#   - Cloud Storage buckets for uploads and backups
#   - Secret Manager versions for runtime secrets
#   - Cloud Run service for the NazmOS API
#   - Cloud Armor security policy + Global HTTPS LB with managed SSL
#
# Run:
#   terraform init -backend-config="bucket=YOUR_STATE_BUCKET"
#   terraform plan -var="project_id=YOUR_PROJECT" -var="container_image=IMAGE_URI"

locals {
  name_prefix = "nazmos-${var.environment}"
  common_labels = {
    product     = "nazmos"
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudkms.googleapis.com",
    "servicenetworking.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ═══════════════════════════════════════════════════════════════════════════
# Networking
# ═══════════════════════════════════════════════════════════════════════════

resource "google_compute_network" "vpc" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${local.name_prefix}-subnet"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id
  private_ip_google_access = true
}

resource "google_vpc_access_connector" "serverless" {
  name          = "${local.name_prefix}-connector"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.8.0.0/28"
  min_throughput = 200
  max_throughput = 1000
}

resource "google_compute_global_address" "private_service_access" {
  name          = "${local.name_prefix}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

# ═══════════════════════════════════════════════════════════════════════════
# Secrets
# ═══════════════════════════════════════════════════════════════════════════

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "random_password" "secret_key" {
  length  = 64
  special = true
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${local.name_prefix}-db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

resource "google_secret_manager_secret" "secret_key" {
  secret_id = "${local.name_prefix}-secret-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = random_password.secret_key.result
}

resource "google_secret_manager_secret" "sentry_dsn" {
  secret_id = "${local.name_prefix}-sentry-dsn"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "sentry_dsn" {
  secret      = google_secret_manager_secret.sentry_dsn.id
  secret_data = var.sentry_dsn
}

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "${local.name_prefix}-openrouter-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "openrouter_api_key" {
  secret      = google_secret_manager_secret.openrouter_api_key.id
  secret_data = var.openrouter_api_key
}

resource "google_secret_manager_secret" "foodics_webhook_secret" {
  secret_id = "${local.name_prefix}-foodics-webhook-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "foodics_webhook_secret" {
  secret      = google_secret_manager_secret.foodics_webhook_secret.id
  secret_data = var.foodics_webhook_secret
}

resource "google_secret_manager_secret" "salla_webhook_secret" {
  secret_id = "${local.name_prefix}-salla-webhook-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "salla_webhook_secret" {
  secret      = google_secret_manager_secret.salla_webhook_secret.id
  secret_data = var.salla_webhook_secret
}

# ═══════════════════════════════════════════════════════════════════════════
# Cloud SQL PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════

resource "google_sql_database_instance" "postgres" {
  name             = "${local.name_prefix}-postgres"
  database_version = var.db_version
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL"
    backup_configuration {
      enabled    = true
      start_time = "03:00"
      point_in_time_recovery_enabled = true
    }
    maintenance_window {
      day  = 7
      hour = 4
    }
    insights_config {
      query_insights_enabled = true
    }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }

  deletion_protection = true

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_sql_database" "nazmos" {
  name     = "nazmos"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "nazmos_app" {
  name     = "nazmos_app"
  instance = google_sql_database_instance.postgres.name
  password = random_password.db_password.result
}

# ═══════════════════════════════════════════════════════════════════════════
# Memorystore Redis
# ═══════════════════════════════════════════════════════════════════════════

resource "google_redis_instance" "redis" {
  name               = "${local.name_prefix}-redis"
  tier               = var.redis_tier
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# ═══════════════════════════════════════════════════════════════════════════
# Object Storage
# ═══════════════════════════════════════════════════════════════════════════

resource "google_storage_bucket" "uploads" {
  name          = "${var.project_id}-${local.name_prefix}-uploads"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 365
    }
  }
}

resource "google_storage_bucket" "backups" {
  name          = "${var.project_id}-${local.name_prefix}-backups"
  location      = var.region
  storage_class = "NEARLINE"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.backups.id
  }
}

# ═══════════════════════════════════════════════════════════════════════════
# KMS for backup encryption
# ═══════════════════════════════════════════════════════════════════════════

resource "google_kms_key_ring" "nazmos" {
  name     = "${local.name_prefix}-keyring"
  location = var.region
}

resource "google_kms_crypto_key" "backups" {
  name            = "${local.name_prefix}-backup-key"
  key_ring        = google_kms_key_ring.nazmos.id
  rotation_period = "7776000s" # 90 days

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "HSM"
  }
}

# ═══════════════════════════════════════════════════════════════════════════
# Service account
# ═══════════════════════════════════════════════════════════════════════════

resource "google_service_account" "api" {
  account_id   = "${local.name_prefix}-api"
  display_name = "NazmOS API runtime service account"
}

resource "google_project_iam_member" "api_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_storage_object_user" {
  project = var.project_id
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ═══════════════════════════════════════════════════════════════════════════
# Cloud Run API service
# ═══════════════════════════════════════════════════════════════════════════

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name_prefix}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.api.email
    vpc_access {
      connector = google_vpc_access_connector.serverless.id
      egress    = "ALL_TRAFFIC"
    }
    scaling {
      min_instances = var.api_min_instances
      max_instances = var.api_max_instances
    }
    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${google_sql_user.nazmos_app.name}:${urlencode(random_password.db_password.result)}@/${google_sql_database.nazmos.name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.redis.host}:6379/0"
      }
      env {
        name  = "USE_CELERY"
        value = "true"
      }
      env {
        name  = "USE_REDIS"
        value = "true"
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "s3"
      }
      env {
        name  = "STORAGE_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "STORAGE_ENDPOINT"
        value = "https://storage.googleapis.com"
      }
      env {
        name  = "SENTRY_ENVIRONMENT"
        value = var.environment
      }

      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SENTRY_DSN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.sentry_dsn.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "OPENROUTER_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openrouter_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "FOODICS_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.foodics_webhook_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SALLA_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.salla_webhook_secret.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.api_secret_accessor,
    google_project_iam_member.api_cloudsql_client,
  ]
}

# ═══════════════════════════════════════════════════════════════════════════
# Load balancer + Cloud Armor + managed SSL
# ═══════════════════════════════════════════════════════════════════════════

resource "google_compute_global_address" "api" {
  name = "${local.name_prefix}-api-ip"
}

resource "google_compute_managed_ssl_certificate" "api" {
  name = "${local.name_prefix}-api-cert"
  managed {
    domains = [var.domain]
  }
}

resource "google_compute_security_policy" "api" {
  name = "${local.name_prefix}-api-policy"

  rule {
    action   = "allow"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Allow all traffic; tighten by country/office IPs in production"
  }

  rule {
    action      = "rate_based_ban"
    priority    = "2000"
    description = "Ban IPs exceeding 100 req/60s"
    match {
      expr {
        expression = "true"
      }
    }
    rate_limit_options {
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
      ban_duration_sec = 300
      conform_action   = "allow"
      exceed_action    = "deny(429)"
      enforce_on_key   = "IP"
    }
  }

  rule {
    action   = "deny(403)"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default deny"
  }
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.name_prefix}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "api" {
  name        = "${local.name_prefix}-api-backend"
  security_policy = google_compute_security_policy.api.id

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }
}

resource "google_compute_url_map" "api" {
  name            = "${local.name_prefix}-api-urlmap"
  default_service = google_compute_backend_service.api.id
}

resource "google_compute_target_https_proxy" "api" {
  name    = "${local.name_prefix}-api-proxy"
  url_map = google_compute_url_map.api.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api.id]
}

resource "google_compute_global_forwarding_rule" "api" {
  name       = "${local.name_prefix}-api-forwarding-rule"
  target     = google_compute_target_https_proxy.api.id
  port_range = "443"
  ip_address = google_compute_global_address.api.address
}

# HTTP -> HTTPS redirect
resource "google_compute_url_map" "http_redirect" {
  name = "${local.name_prefix}-api-http-redirect"
  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "http_redirect" {
  name    = "${local.name_prefix}-api-http-proxy"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  name       = "${local.name_prefix}-api-http-forward"
  target     = google_compute_target_http_proxy.http_redirect.id
  port_range = "80"
  ip_address = google_compute_global_address.api.address
}
