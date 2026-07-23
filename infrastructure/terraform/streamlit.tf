# 1. Provision Artifact Registry repository to host your custom Streamlit image
resource "google_artifact_registry_repository" "app_repo" {
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  description   = "Docker repository for Streamlit frontend apps"
  format        = "DOCKER"
}

# 2. Provision the serverless Cloud Run container service1
resource "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # Points to the built image tag in your registry
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/${google_artifact_registry_repository.app_repo.repository_id}/streamlit-frontend:latest"

      ports {
        container_port = 8080 # Standard port for Streamlit apps
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

# 4. CRITICAL IAM: Grant Vertex AI User permissions to your Agent Service Account
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-661224241135@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
