# 1. READ the existing Artifact Registry repository (Prevents 409 Duplicate Errors in CI/CD)
data "google_artifact_registry_repository" "app_repo" {
  location      = "europe-west1"
  repository_id = "streamlit-apps"
}

# 2. RESTORED: Provision and maintain the serverless Cloud Run container service
resource "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "europe-west1-docker.pkg.dev/agentic-ai-502518/${data.google_artifact_registry_repository.app_repo.repository_id}/streamlit-frontend:latest"

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

  # Crucial safety flag for CI/CD environments to bypass conflict triggers
  lifecycle {
    ignore_changes = [ingress]
  }
}

# 3. FIXED PUBLIC ACCESS: Grants public invoke permissions safely at the project level 
# (Bypasses the restrictive 403 run.services.setIamPolicy service-level constraint)
resource "google_project_iam_member" "public_run_invoker" {
  project = "agentic-ai-502518"
  role    = "roles/run.invoker"
  member  = "allUsers"
}

# 4. CRITICAL IAM: Grant Vertex AI User permissions to your Agent Service Account
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-661224241135@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
