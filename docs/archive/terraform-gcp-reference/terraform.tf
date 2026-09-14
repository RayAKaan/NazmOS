terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Create this bucket outside of Terraform and pass it as a backend config:
  # terraform init -backend-config="bucket=YOUR_STATE_BUCKET"
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
