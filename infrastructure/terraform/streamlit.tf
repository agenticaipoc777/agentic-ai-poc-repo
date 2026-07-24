# 1. AUTOMATIC IMPORT: Adopts your existing Cloud Run service safely into Terraform state
import {
  to = google_cloud_run_v2_service.streamlit_service
  id = "projects/agentic-ai-502518/locations/europe-west1/services/bq-analytics-frontend"
}

# 2. Maintain the existing serverless Cloud Run container service
resource "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # FIXED: Hardcoded your existing cloud container image path to prevent registry checks
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
}

# 3. PUBLIC ACCESS: Maintained cleanly to keep your app public
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = "agentic-ai-502518"
  location = "europe-west1"
  name     = google_cloud_run_v2_service.streamlit_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 4. FIXED: Your exact, required Google-Managed Service Agent left completely untouched
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-661224241135@://gserviceaccount.com"
}
