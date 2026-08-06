# ====================================================================
# LLM CHAT: Artifact Registry + GPU-enabled Cloud Run service
# ====================================================================

# Cloud Run GPU support requires the google-beta provider per Google's
# own current documentation for this feature -- the stable "google"
# provider's google_cloud_run_v2_service resource does not yet expose
# the GPU-specific fields (node_selector, gpu_zonal_redundancy_disabled)
# the same way. Minimal block below assumes the same project/region as
# the rest of this config; if your main "google" provider block sets
# explicit credentials, mirror those here too.
provider "google-beta" {
  project = var.project_id
  region  = var.vertex_compute_region
}

resource "google_artifact_registry_repository" "llm_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "llm-apps"
  format        = "DOCKER"
  description   = "Docker repository for the local LLM chat app (large images -- model weights baked in)"
}

resource "google_cloud_run_v2_service" "llm_chat" {
  provider = google-beta
  project  = var.project_id
  name     = "local-llm-chat"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = "adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"

    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = "${var.vertex_compute_region}-docker.pkg.dev/${var.project_id}/llm-apps/local-llm-chat:${var.llm_image_tag}"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu              = "4"
          memory           = "16Gi"
          "nvidia.com/gpu" = "1"
        }
        startup_cpu_boost = true
      }

      startup_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 10
        period_seconds        = 15
        failure_threshold     = 20
        tcp_socket {
          port = 8080
        }
      }

      env {
        name  = "MODEL_ID"
        value = var.llm_model_id
      }
      env {
        name  = "USE_4BIT_QUANTIZATION"
        value = var.llm_use_4bit_quantization
      }
    }

    timeout = "300s"

    node_selector {
      accelerator = "nvidia-l4"
    }

    gpu_zonal_redundancy_disabled = true
  }

  lifecycle {
    ignore_changes = [ingress]
  }
}