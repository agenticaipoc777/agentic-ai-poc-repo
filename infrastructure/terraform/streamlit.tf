# 1. ARTIFACT REGISTRY: Create and maintain the secure Docker repository
resource "google_artifact_registry_repository" "app_repo" {
  project       = "agentic-ai-502518"
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}

# 2. SERVICE ACCOUNT BINDING: Allows your personal user to deploy using the service account identity
resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}

# 3. CLOUD RUN SERVICE: Builds a clean instance running strictly under adk-agent-runner
resource "google_cloud_run_v2_service" "streamlit_service" {
  project    = "agentic-ai-502518"
  name       = "bq-analytics-frontend"
  location   = "europe-west1"
  ingress    = "INGRESS_TRAFFIC_ALL"

  template {
    # Assigning runtime identity to the service account
    service_account = "adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"

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

  # Ensure the IAM permission exists before attempting creation
  depends_on = [google_service_account_iam_member.deployer_impersonation]
}

# 4. FIXED PUBLIC INTERNET ROUTING: Allows unauthenticated access to the application
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = "agentic-ai-502518"
  location = "europe-west1"
  name     = google_cloud_run_v2_service.streamlit_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 5. VERTEX AI PRIVILEGES: Grants the runtime service account execution permissions
resource "google_project_iam_member" "runner_vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}

# 6. ARTIFACT REGISTRY PRIVILEGES: Grants the runtime service account permission to pull images
resource "google_artifact_registry_repository_iam_member" "runner_registry_reader" {
  project    = "agentic-ai-502518"
  location   = google_artifact_registry_repository.app_repo.location
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}
