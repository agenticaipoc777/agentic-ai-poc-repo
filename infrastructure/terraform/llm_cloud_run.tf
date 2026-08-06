# ====================================================================
# IMPORTS: these two resources already exist in GCP (created by a
# prior pipeline run) but Terraform's state didn't know about them,
# causing "already exists" 409 errors on apply. Same pattern already
# used at the top of this project's main Terraform file for the same
# reason -- import them once so Terraform manages the real resources
# instead of trying to recreate them.
# ====================================================================
import {
  to = google_artifact_registry_repository.llm_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/llm-apps"
}

import {
  to = google_cloud_run_v2_service.llm_chat
  id = "projects/agentic-ai-502518/locations/europe-west1/services/local-llm-chat"
}

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

    # GPUs require Gen2 execution environment -- Gen1 does not support
    # them. Omitting this is a documented common mistake that fails
    # with an unhelpful error message.
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    # ENHANCEMENT: min_instance_count = 0 means this genuinely shuts
    # down (stops being billed) when nobody's using it -- Cloud Run
    # GPU billing tracks actual running time, not a reserved
    # allocation, so an idle service with zero instances costs
    # nothing. Tradeoff, stated plainly: the FIRST request after an
    # idle period pays the full cold-start cost -- pulling the large
    # baked-model image, initializing CUDA, and loading the model
    # into VRAM. That's realistically 1-3+ minutes for a 7B model,
    # not seconds. The startup_probe and timeout settings below give
    # that process room to actually finish instead of Cloud Run
    # killing the instance or the request timing out mid-load -- they
    # don't make the cold start itself faster. If that latency is
    # unacceptable for your use case, min_instance_count = 1 trades
    # the ~$0.67/hr always-on cost for eliminating it -- your call
    # based on actual usage pattern.
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

      # Generous startup allowance -- default Cloud Run assumptions
      # are tuned for lightweight web services that start in seconds,
      # not a GPU instance that needs to pull a multi-GB image and
      # load model weights into VRAM before it's actually ready.
      # Without this, Cloud Run can mark a genuinely-still-starting
      # instance as failed and kill it before the model finishes
      # loading.
      startup_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 10
        period_seconds        = 15
        failure_threshold     = 20  # ~30s + 20*15s = up to ~330s to become ready
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

    # Also generous, for the same cold-start reason: the first
    # request into a freshly-started instance may need to wait for
    # model loading to actually finish (Streamlit's own port can bind
    # before @st.cache_resource's model load completes) -- a short
    # request timeout would cut that first request off mid-load.
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
