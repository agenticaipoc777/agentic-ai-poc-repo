# 1. READ the existing Artifact Registry repository (Prevents 409 Duplicate Errors)
resource "google_artifact_registry_repository" "app_repo" {
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}

# 2. AUTOMATIC IMPORT: Adopts the existing Cloud Run service safely into CI/CD pipeline state
import {
  to = google_cloud_run_v2_service.streamlit_service
  id = "projects/agentic-ai-502518/locations/europe-west1/services/bq-analytics-frontend"
}

# 3. Provision and maintain the serverless Cloud Run container service resources
resource "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/${google_artifact_registry_repository.app_repo.repository_id}/streamlit-frontend:latest"

      ports {
        container_port = 8080 # Matches your Dockerfile configuration
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

# 4. PUBLIC ACCESS: Keep your frontend live and accessible to users over the web#
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = "agentic-ai-502518"
  location = "europe-west1"
  name     = google_cloud_run_v2_service.streamlit_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 5. FIXED: Using your real, existing adk-agent-runner service account
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}
