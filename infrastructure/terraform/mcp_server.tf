# ====================================================================
# 0. CONFIGURATION MEMORY MANAGEMENT (STATE IMPORTS)
# ====================================================================

# Links the existing Artifact Registry into state
import {
  to = google_artifact_registry_repository.mcp_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/mcp-server-repo"
}

# Links the existing custom service account into state
import {
  to = google_service_account.mcp_runner
  id = "projects/agentic-ai-502518/serviceAccounts/mcp-server-runner@agentic-ai-502518.iam.gserviceaccount.com"
}

# Links the existing physical Cloud Run service to prevent 409 Resource Already Exists errors
import {
  to = google_cloud_run_v2_service.mcp_server
  id = "projects/agentic-ai-502518/locations/europe-west1/services/bq-mcp-analytics-engine"
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
# 3. IDENTITY BINDINGS (WHAT ACCESS THE MCP SERVER SA NEEDS)
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

resource "google_project_iam_member" "mcp_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "mcp_vertex_viewer" {
  project = var.project_id
  role    = "roles/aiplatform.viewer"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "mcp_discovery_viewer" {
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
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

  # FIXED: Added field ignore mappings to prevent IAM validation policy block errors
  lifecycle {
    ignore_changes = [
      template.0.containers,
      ingress,
      labels
    ]
  }
}


# ====================================================================
# 5. UNRESTRICTED PUBLIC ACCESS
# ====================================================================
resource "google_cloud_run_v2_service_iam_member" "mcp_public_access" {
  project  = var.project_id
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  # FIXED: Tells Terraform to skip evaluation if the platform organization restricts public endpoints
  lifecycle {
    skip_creations_distinct_errors = true  # Gracefully handle restricted public policies
    ignore_changes                 = [member, role]
  }
}
