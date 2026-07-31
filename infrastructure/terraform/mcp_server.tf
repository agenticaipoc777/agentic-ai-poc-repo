# ====================================================================
# 0. CONFIGURATION MEMORY MANAGEMENT (STATE IMPORTS)
# ====================================================================

# Links the existing Artifact Registry into state
import {
  to = google_artifact_registry_repository.mcp_repo
  id = "projects/agentic-ai-502518/locations/europe-west1/repositories/mcp-server-repo"
}

# Adopt existing service account identity safely
import {
  to = google_service_account.mcp_runner
  id = "projects/agentic-ai-502518/serviceAccounts/mcp-server-runner@://gserviceaccount.com"
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

# Role A: Allows the MCP Server to run queries and manage compute tasks
resource "google_project_iam_member" "mcp_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

# Role B: Allows the MCP Server to read actual row data inside BigQuery datasets
resource "google_project_iam_member" "mcp_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

# Role C: Grants core machine learning resource invocation rights
resource "google_project_iam_member" "mcp_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

# Role D: NEW - Grants explicit permission to inspect metadata on reasoning engine pipelines
resource "google_project_iam_member" "mcp_vertex_viewer" {
  project = var.project_id
  role    = "roles/aiplatform.viewer"
  member  = "serviceAccount:mcp-server-runner@${var.project_id}.iam.gserviceaccount.com"
}

# Role E: NEW - Resolves Discovery Engine / Agent Builder validation checks used by modern vertexai SDKs
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
  
  # YES - This is required to let the internet route traffic to the container port
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
      template.containers
    ]
  }
}


# ====================================================================
# 5. UNRESTRICTED PUBLIC ACCESS: Changes "Require authentication" to "Public access"
# ====================================================================
resource "google_cloud_run_v2_service_iam_member" "mcp_public_access" {
  project  = var.project_id
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  member   = "allUsers" # 👈 Force opens public routing, bypassing the 403 Forbidden error
}

