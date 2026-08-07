# ====================================================================
# IMPORTS: these three already exist in GCP/GKE (most likely from the
# earlier "Queued" workflow run that eventually completed in the
# background while a separate retry also ran) but Terraform's state
# for THIS run's plan didn't know about them, causing 409 "already
# exists" errors on apply. Same fix pattern already used for the
# bq_pg_proxy and llm resources in this project.
# ====================================================================
import {
  to = google_artifact_registry_repository.agent_noadk_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/agent-noadk-apps"
}

import {
  to = kubernetes_service_account_v1.agent_noadk_sa
  id = "default/agent-noadk-sa"
}

import {
  to = kubernetes_service_v1.agent_noadk_service
  id = "default/agent-noadk-service"
}

# ====================================================================
# AGENT_NOADK: direct Kubernetes deployment (no Cloud Run) --
# Gemini 2.5 BigQuery agent dashboard, no ADK.
# ====================================================================

resource "google_artifact_registry_repository" "agent_noadk_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "agent-noadk-apps"
  format        = "DOCKER"
  description   = "Docker repository for the no-ADK Gemini BigQuery agent"
}

resource "kubernetes_service_account_v1" "agent_noadk_sa" {
  metadata {
    name      = "agent-noadk-sa"
    namespace = "default"
    annotations = {
      # Reuses the same real GCP identity already established
      # throughout this project (adk-agent-runner) -- already has
      # BigQuery Data Viewer / Job User, and Vertex AI access is
      # added below.
      "iam.gke.io/gcp-service-account" = "adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
    }
  }
}

resource "google_service_account_iam_member" "agent_noadk_workload_identity" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role                = "roles/iam.workloadIdentityUser"
  member              = "serviceAccount:${var.project_id}.svc.id.goog[default/agent-noadk-sa]"
}

# adk-agent-runner already has BigQuery access from earlier in this
# project; Vertex AI (Gemini) access is new for this specific agent.
resource "google_project_iam_member" "agent_noadk_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
}

resource "kubernetes_deployment_v1" "agent_noadk" {
  metadata {
    name      = "agent-noadk"
    namespace = "default"
    labels    = { app = "agent-noadk" }
  }

  spec {
    replicas = 2  # start at 2 for basic availability; HPA scales beyond this under load

    selector {
      match_labels = { app = "agent-noadk" }
    }

    template {
      metadata {
        labels = { app = "agent-noadk" }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.agent_noadk_sa.metadata[0].name

        container {
          name  = "agent-noadk"
          image = "${var.vertex_compute_region}-docker.pkg.dev/${var.project_id}/agent-noadk-apps/agent-noadk:${var.agent_noadk_image_tag}"

          port {
            container_port = 8080
          }

          # No GPU needed -- this workload calls Vertex AI's Gemini
          # API and BigQuery, both remote services; the pod itself
          # does no local model inference. Sized for a chat/dashboard
          # workload, not compute-heavy processing.
          resources {
            requests = {
              cpu    = "500m"
              memory = "1Gi"
            }
            limits = {
              cpu    = "2"
              memory = "2Gi"
            }
          }

          readiness_probe {
            tcp_socket { port = 8080 }
            initial_delay_seconds = 10
            period_seconds        = 10
          }
          liveness_probe {
            tcp_socket { port = 8080 }
            initial_delay_seconds = 20
            period_seconds        = 20
          }
        }
      }
    }
  }
}

# Horizontal Pod Autoscaler -- handles concurrent dashboard users
# without needing to manually size replica count; the underlying
# 10-billion-row scale is handled by BigQuery itself, not by scaling
# this app tier, but concurrent USER load still benefits from
# autoscaling this front-end.
resource "kubernetes_horizontal_pod_autoscaler_v2" "agent_noadk_hpa" {
  metadata {
    name      = "agent-noadk-hpa"
    namespace = "default"
  }
  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.agent_noadk.metadata[0].name
    }
    min_replicas = 2
    max_replicas = 10

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "agent_noadk_service" {
  metadata {
    name      = "agent-noadk-service"
    namespace = "default"
    annotations = {
      "networking.gke.io/load-balancer-type" = "Internal"
    }
  }
  spec {
    selector = { app = "agent-noadk" }
    port {
      port        = 80
      target_port = 8080
    }
    type = "LoadBalancer"
  }
}
