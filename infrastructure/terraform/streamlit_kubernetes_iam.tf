# ====================================================================
# 0. AUTOMATED IMPORTS: Dynamic resource mapping
# ====================================================================

import {
  to = google_artifact_registry_repository.app_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/streamlit-apps"
}

import {
  to = google_workbench_instance.adk_predictive_workbench
  id = "projects/agentic-ai-502518/locations/europe-west1-b/instances/adk-predictive-analysis-instance"
}

import {
  to = google_container_cluster.gke_cluster
  id = "projects/agentic-ai-502518/locations/europe-west1/clusters/adk-analytics-gke-cluster"
}

import {
  to = google_cloud_run_v2_service.streamlit_service
  id = "projects/agentic-ai-502518/locations/europe-west1/services/bq-analytics-frontend"
}


# ====================================================================
# 1. VERTEX AI WORKBENCH: Machine learning workspace setup
# ====================================================================
resource "google_workbench_instance" "adk_predictive_workbench" {
  name     = "adk-predictive-analysis-instance"
  project  = var.project_id
  location = "${var.vertex_compute_region}-b" # Appends the zone dynamically to your compute region
}


# ====================================================================
# 2. ARTIFACT REGISTRY: Shared Docker repository for Streamlit images for docker
# ====================================================================
resource "google_artifact_registry_repository" "app_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}


# ====================================================================
# 3. GKE KUBERNETES CLUSTER: Autopilot engine
# ====================================================================
resource "google_container_cluster" "gke_cluster" {
  name             = "adk-analytics-gke-cluster"
  project          = var.project_id
  location         = var.vertex_compute_region
  enable_autopilot = true

  network    = "projects/${var.project_id}/global/networks/default"
  subnetwork = "projects/${var.project_id}/regions/${var.vertex_compute_region}/subnetworks/default"

  ip_allocation_policy {
    cluster_ipv4_cidr_block  = ""
    services_ipv4_cidr_block = ""
  }
}


# ====================================================================
# 4. CLOUD RUN SERVICE: Serverless frontend option
# ====================================================================
resource "google_cloud_run_v2_service" "streamlit_service" {
  project  = var.project_id
  name     = "bq-analytics-frontend"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    # Uses your explicit requested service account email address with variable interpolation
    service_account = "adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"

    containers {
      image = "${var.vertex_compute_region}-docker.pkg.dev/${var.project_id}/streamlit-apps/streamlit-frontend:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [ingress]
  }

  depends_on = [google_service_account_iam_member.deployer_impersonation]
}

# ====================================================================
# 5 DYNAMIC IMPORTS: Handle existing duplicates automatically
# ====================================================================
import {
  to = kubernetes_deployment_v1.bq_pg_proxy
  id = "default/bq-pg-proxy"
}

import {
  to = kubernetes_service_v1.bq_pg_proxy_service
  id = "default/bq-pg-proxy-service"
}

# ====================================================================
# 6. KUBERNETES MANIFEST MANAGE: Automated cluster workload deployment
# ====================================================================
resource "kubernetes_deployment_v1" "bq_pg_proxy" {
  metadata {
    name      = "bq-pg-proxy"
    namespace = "default"
    labels = {
      app = "bq-pg-proxy"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "bq-pg-proxy"
      }
    }

    template {
      metadata {
        labels = {
          app = "bq-pg-proxy"
        }
      }

      spec {
        container {
          name  = "proxy-engine"
          image = "europe-west1-docker.pkg.dev/agentic-ai-502518/bq-pg-proxy-repo/bq-pg-proxy-app:latest"
          
          port {
            container_port = 5432
          }

          env {
            name  = "PG_PROXY_LISTEN_HOST"
            value = "0.0.0.0"
          }
          env {
            name  = "PG_PROXY_LISTEN_PORT"
            value = "5432"
          }
          env {
            name  = "PG_PROXY_PROJECT_ID"
            value = "agentic-ai-502518"
          }
          env {
            name  = "PG_PROXY_LOCATION"
            value = "europe-west1"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "bq_pg_proxy_service" {
  metadata {
    name      = "bq-pg-proxy-service"
    namespace = "default"
  }
  spec {
    selector = {
      app = "bq-pg-proxy"
    }
    port {
      port        = 5432
      target_port = 5432
    }
    type = "ClusterIP"
  }
}

