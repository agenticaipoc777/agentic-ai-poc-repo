# ====================================================================
# 0. AUTOMATED IMPORTS: Maps all existing GCP resources into your state
# ====================================================================

import {
  to = google_service_account.agent_runner
  id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@://gserviceaccount.com"
}

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
# 1. CORE IDENTITY: Service Account Creation & Management
# ====================================================================
resource "google_service_account" "agent_runner" {
  project      = "agentic-ai-502518"
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Runner Service Account"
  description  = "Managed runtime service account for GKE and Cloud Run Streamlit apps"
}


# ====================================================================
# 2. VERTEX AI WORKBENCH: Machine learning workspace setup
# ====================================================================
resource "google_workbench_instance" "adk_predictive_workbench" {
  name     = "adk-predictive-analysis-instance"
  project  = "agentic-ai-502518"
  location = "europe-west1-b"
}


# ====================================================================
# 3. ARTIFACT REGISTRY: Shared Docker repository for Streamlit images
# ====================================================================
resource "google_artifact_registry_repository" "app_repo" {
  project       = "agentic-ai-502518"
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}


# ====================================================================
# 4. GKE KUBERNETES CLUSTER: Autopilot engine
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
# 5. CLOUD RUN SERVICE: Serverless frontend option
# ====================================================================
resource "google_cloud_run_v2_service" "streamlit_service" {
  project  = "agentic-ai-502518"
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    # Programmatically binds the service account email
    service_account = google_service_account.agent_runner.email

    containers {
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/${google_artifact_registry_repository.app_repo.repository_id}/streamlit-frontend:latest"

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
# 6. PUBLIC ROUTING: Allows anonymous web entry to Cloud Run
# ====================================================================
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = "agentic-ai-502518"
  location = "europe-west1"
  name     = google_cloud_run_v2_service.streamlit_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ====================================================================
# 7. IDENTITY BINDINGS: Maps structural runtime parameters securely
# ====================================================================

# Workload Identity: Links your GKE deployment pods to the runner account
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = google_service_account.agent_runner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:agentic-ai-502518.svc.id.goog[default/streamlit-service-account]"
}

# Deployer Impersonation: Grants explicit manual invocation privileges 
resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = google_service_account.agent_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}

# Vertex AI Access: Allows the core service account executing backend queries
resource "google_project_iam_member" "runner_vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

# Artifact Registry Reader: Authorizes pulling backend container assets
resource "google_artifact_registry_repository_iam_member" "runner_registry_reader" {
  project    = "agentic-ai-502518"
  location   = google_artifact_registry_repository.app_repo.location
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.agent_runner.email}"
}
