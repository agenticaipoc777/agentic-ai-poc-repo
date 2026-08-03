# ====================================================================
# 0. AUTOMATED IMPORTS: Dynamic resource mapping
# ====================================================================

import {
  to = google_artifact_registry_repository.app_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/streamlit-apps"
}

import {
  to = google_artifact_registry_repository.pg_proxy_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/bq-pg-proxy-repo"
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

# Duplicate resolution imports for Kubernetes workloads
import {
  to = kubernetes_deployment_v1.bq_pg_proxy
  id = "default/bq-pg-proxy"
}

import {
  to = kubernetes_service_v1.bq_pg_proxy_service
  id = "default/bq-pg-proxy-service"
}

# FIXED: Added to resolve the duplicate service account conflict automatically
import {
  to = kubernetes_service_account_v1.proxy_sa
  id = "default/bq-pg-proxy-sa"
}


# ====================================================================
# KUBERNETES PROVIDER CONFIGURATION
# ====================================================================
data "google_client_config" "default" {}

data "google_container_cluster" "my_gke" {
  name     = "adk-analytics-gke-cluster"
  project  = var.project_id
  location = var.vertex_compute_region
}

provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.my_gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(data.google_container_cluster.my_gke.master_auth[0].cluster_ca_certificate)
}


# ====================================================================
# 1. VERTEX AI WORKBENCH
# ====================================================================
resource "google_workbench_instance" "adk_predictive_workbench" {
  name     = "adk-predictive-analysis-instance"
  project  = var.project_id
  location = "${var.vertex_compute_region}-b" 
}


# ====================================================================
# 2. ARTIFACT REGISTRY
# ====================================================================
resource "google_artifact_registry_repository" "app_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}

resource "google_artifact_registry_repository" "pg_proxy_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "bq-pg-proxy-repo"
  format        = "DOCKER"
  description   = "Docker repository for the Postgres-BigQuery proxy service"
}


# ====================================================================
# 3. GKE KUBERNETES CLUSTER
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
# 4. CLOUD RUN SERVICE
# ====================================================================
resource "google_cloud_run_v2_service" "streamlit_service" {
  project  = var.project_id
  name     = "bq-analytics-frontend"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
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
}


# ====================================================================
# 5. WORKLOAD IDENTITY MAPPING & MANIFEST MANAGEMENT
# ====================================================================
resource "kubernetes_service_account_v1" "proxy_sa" {
  metadata {
    name      = "bq-pg-proxy-sa"
    namespace = "default"
    annotations = {
      "iam.gke.io/gcp-service-account" = "adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
    }
  }
}

resource "google_service_account_iam_member" "gke_workload_identity_binding" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/bq-pg-proxy-sa]"
}

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
        service_account_name = kubernetes_service_account_v1.proxy_sa.metadata.name

        container {
          name  = "proxy-engine"
          image = "${var.vertex_compute_region}-docker.pkg.dev/${var.project_id}/bq-pg-proxy-repo/bq-pg-proxy-app:latest"
          
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
            value = var.project_id
          }
          env {
            name  = "PG_PROXY_LOCATION"
            value = var.vertex_compute_region
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
    type = "LoadBalancer"
  }
}
