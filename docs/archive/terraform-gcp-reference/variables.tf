variable "project_id" {
  description = "GCP project ID for NazmOS production infrastructure"
  type        = string
}

variable "region" {
  description = "GCP region for production workloads (KSA / me-central2 recommended)"
  type        = string
  default     = "me-central2"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "production"
}

variable "domain" {
  description = "Primary public API domain"
  type        = string
  default     = "app.nazm.ai"
}

variable "container_image" {
  description = "NazmOS API container image URI"
  type        = string
}

variable "api_min_instances" {
  description = "Minimum Cloud Run instances"
  type        = number
  default     = 1
}

variable "api_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 10
}

variable "db_tier" {
  description = "Cloud SQL PostgreSQL machine tier"
  type        = string
  default     = "db-g1-small"
}

variable "db_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "POSTGRES_16"
}

variable "redis_tier" {
  description = "Memorystore Redis tier"
  type        = string
  default     = "STANDARD_HA"
}

variable "redis_memory_gb" {
  description = "Memorystore Redis capacity in GiB"
  type        = number
  default     = 5
}

variable "cors_origins" {
  description = "Comma-separated allowed CORS origins for the API"
  type        = string
  default     = "https://app.nazm.ai,https://nazm.ai"
}

variable "sentry_dsn" {
  description = "Sentry DSN for production error tracking"
  type        = string
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "OpenRouter API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "foodics_webhook_secret" {
  description = "Foodics webhook HMAC secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "salla_webhook_secret" {
  description = "Salla webhook HMAC secret"
  type        = string
  sensitive   = true
  default     = ""
}
