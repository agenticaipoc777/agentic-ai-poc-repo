# ====================================================================
# 0. AUTOMATED IMPORTS: Pulls existing GCP resources into state
# ====================================================================
import {
  to = google_service_account.agent_runner
  id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}

import {
  to = google_artifact_registry_repository.app_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/streamlit-apps"
}

# ====================================================================
# 1. CORE IDENTITY: Service Account management
# ====================================================================
resource "google_service_account" "agent_runner" {
  project      = "agentic-ai-502518"
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Runner Service Account"
  description  = "Managed runtime service account for GKE and Cloud Run Streamlit apps"
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
# 4. CLOUD RUN SERVICE: Serverless hosting option
# ====================================================================
resource "google_cloud_run_v2_service" "streamlit_service" {
  project  = "agentic-ai-502518"
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    # Dynamically reads the clean email string from your resource configuration
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
# 5. CLOUD RUN IAM: Public internet access configuration
# ====================================================================
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = "agentic-ai-502518"
  location = "europe-west1"
  name     = google_cloud_run_v2_service.streamlit_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ====================================================================
# 6. IAM & SECURITY BINDINGS
# ====================================================================

# Workload Identity: Links GKE pods to your exact runner account
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = google_service_account.agent_runner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:agentic-ai-502518.svc.id.goog[default/streamlit-service-account]"
}

# Deployer Impersonation: Allows you to deploy manually using the runner identity
resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = google_service_account.agent_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}

# Vertex AI Access: Runtime execution permission for the runner
resource "google_project_iam_member" "runner_vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runner.email}"
}

# Artifact Registry Reader: Permits the runner to pull custom Docker images
resource "google_artifact_registry_repository_iam_member" "runner_registry_reader" {
  project    = "agentic-ai-502518"
  location   = google_artifact_registry_repository.app_repo.location
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.agent_runner.email}"
}
