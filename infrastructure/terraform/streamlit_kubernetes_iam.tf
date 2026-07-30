# ====================================================================
# 0. AUTOMATED IMPORTS: Maps existing infra without touching vertex_ai assets
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
  project  = "agentic-ai-502518"
  location = "europe-west1-b"
}


# ====================================================================
# 2. ARTIFACT REGISTRY: Shared Docker repository for Streamlit images
# ====================================================================
resource "google_artifact_registry_repository" "app_repo" {
  project       = "agentic-ai-502518"
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}


# ====================================================================
# 3. GKE KUBERNETES CLUSTER: Autopilot engine
# ====================================================================
resource "google_container_cluster" "gke_cluster" {
  name             = "adk-analytics-gke-cluster"
  project          = "agentic-ai-502518"
  location         = "europe-west1"
  enable_autopilot = true

  network    = "projects/agentic-ai-502518/global/networks/default"
  subnetwork = "projects/agentic-ai-502518/regions/europe-west1/subnetworks/default"

  ip_allocation_policy {
    cluster_ipv4_cidr_block  = ""
    services_ipv4_cidr_block = ""
  }
}


# ====================================================================
# 4. CLOUD RUN SERVICE: Serverless frontend option
# ====================================================================
resource "google_cloud_run_v2_service" "streamlit_service" {
  project  = "agentic-ai-502518"
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    # VERIFIED: Using your exact service account email address explicitly
    service_account = "adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"

    containers {
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/streamlit-apps/streamlit-frontend:latest"

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
# 5. IDENTITY BINDINGS USING STATIC SERVICE ACCOUNT VALUES
# ====================================================================

# Workload Identity: Links your GKE deployment pods to your exact runner account
resource "google_service_account_iam_member" "gke_workload_identity" {
  # VERIFIED: Using your exact service account identifier path
  service_account_id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:agentic-ai-502518.svc.id.goog[default/streamlit-service-account]"
}

# Deployer Impersonation: Grants manual invocation privileges over your exact runner account
resource "google_service_account_iam_member" "deployer_impersonation" {
  # VERIFIED: Using your exact service account identifier path
  service_account_id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}
