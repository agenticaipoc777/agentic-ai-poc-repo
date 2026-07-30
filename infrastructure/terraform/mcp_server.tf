# 1. Create a secure Docker repository inside Artifact Registry
resource "google_artifact_registry_repository" "mcp_repo" {
  location      = var.vertex_compute_region
  repository_id = "mcp-server-repo"
  description   = "Docker repository hosting our custom MCP web apps"
  format        = "DOCKER"
}

# 2. Create the runtime identity for the MCP server
resource "google_service_account" "mcp_runner" {
  account_id   = "mcp-server-runner"
  display_name = "MCP Server Cloud Run Service Account"
}

# 3. Assign necessary roles to the service account
resource "google_project_iam_member" "mcp_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.mcp_runner.email}"
}

resource "google_project_iam_member" "mcp_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.mcp_runner.email}"
}

# 4. Provision the Cloud Run serverless engine
resource "google_cloud_run_v2_service" "mcp_server" {
  name     = "bq-mcp-analytics-engine"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.mcp_runner.email
    
    containers {
      # FIXED: Use a universally available public placeholder image for the initial deployment boost
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"
      
      ports {
        container_port = 8080
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

# 5. Enforce Zero-Trust Authentication (Block anonymous web access)
resource "google_cloud_run_v2_service_iam_binding" "mcp_no_auth" {
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  members = [
    "serviceAccount:${google_service_account.mcp_runner.email}"
  ]
}
