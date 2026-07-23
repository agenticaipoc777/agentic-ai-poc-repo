# 1. READ the existing Artifact Registry repository (Prevents 409 Duplicate Errors in CI/CD)
data "google_artifact_registry_repository" "app_repo" {
  location      = "europe-west1"
  repository_id = "streamlit-apps"
}

# 2. Provision the serverless Cloud Run container service
resource "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/${data.google_artifact_registry_repository.app_repo.repository_id}/streamlit-frontend:latest"

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
}

# 3. Securely bind public view access to the Streamlit UI web address
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  name     = google_cloud_run_v2_service.streamlit_service.name
  location = google_cloud_run_v2_service.streamlit_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 4. CRITICAL IAM: Fixed explicit Service Account formatting to prevent cloud API rejection
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-661224241135@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
