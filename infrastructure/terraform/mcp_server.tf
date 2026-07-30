# ====================================================================
# 0. CONFIGURATION MEMORY MANAGEMENT (STATE IMPORTS)
# ====================================================================

# Links the existing Artifact Registry into state
import {
  to = google_artifact_registry_repository.mcp_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/mcp-server-repo"
}

# FULLY FIXED: Eliminated the broken text formatting string completely
import {
  to = google_service_account.mcp_runner
  id = "projects/agentic-ai-502518/serviceAccounts/mcp-server-runner@agentic-ai-502518.iam.gserviceaccount.com"
}


# ====================================================================
# 1. CORE ARTIFACT REPOSITORY
# ====================================================================
resource "google_artifact_registry_repository" "mcp_repo" {
  project       = var.project_id
  location      = var.vertex_compute_region
  repository_id = "mcp-server-repo"
  description   = "Docker repository hosting our custom MCP web apps"
  format        = "DOCKER"
}


# ====================================================================
# 2. RUNTIME IDENTITY (THE RUNNER IDENTITY)
# ====================================================================
resource "google_service_account" "mcp_runner" {
  project      = var.project_id
  account_id   = "mcp-server-runner"
  display_name = "MCP Server Cloud Run Service Account"
}


# ====================================================================
# 3. IDENTITY BINDINGS (DATA ACCESS ENGINES)
# ====================================================================
resource "google_project_iam_member" "mcp_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "mcp_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}


# ====================================================================
# 4. SERVERLESS ENGINE PROVISIONING
# ====================================================================
resource "google_cloud_run_v2_service" "mcp_server" {
  project  = var.project_id
  name     = "bq-mcp-analytics-engine"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = "mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

      ports {
        container_port = 8080
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers
    ]
  }
}


# ====================================================================
# 5. ACCESS CONTROLS (SECURE INBOUND ENTRANCES)
# ====================================================================
resource "google_cloud_run_v2_service_iam_binding" "mcp_no_auth" {
  project  = var.project_id
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  members = [
    "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com",
    "user:lakshmikanth.avh1b@gmail.com" # FIXED: Added your user account so you bypass the 403 error page
  ]
}
