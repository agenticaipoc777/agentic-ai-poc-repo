# 1. Create a secure Docker repository inside Artifact Registry (Uses compute region)
resource "google_artifact_registry_repository" "mcp_repo" {
  location      = var.vertex_compute_region
  repository_id = "mcp-server-repo"
  description   = "Docker repository hosting our custom MCP web apps"
  format        = "DOCKER"
}

# 2. CREATE THE RUNTIME IDENTITY FOR THE MCP SERVER
resource "google_service_account" "mcp_runner" {
  account_id   = "mcp-server-runner"
  display_name = "MCP Server Cloud Run Service Account"
}

# 3. ASSIGN NECESSARY ROLES TO THE SERVICE ACCOUNT
# Role A: Allows the MCP Server to execute queries, slots, and interactive jobs
resource "google_project_iam_member" "mcp_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.mcp_runner.email}"
}

# Role B: Allows the MCP Server to read schemas and metadata from your data rows
resource "google_project_iam_member" "mcp_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.mcp_runner.email}"
}

# 4. Provision the Cloud Run serverless engine (Uses compute region)
resource "google_cloud_run_v2_service" "mcp_server" {
  name     = "bq-mcp-analytics-engine"
  location = var.vertex_compute_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    # Attach our newly created dedicated service account identity here
    service_account = google_service_account.mcp_runner.email

    containers {
      # Points directly to our Artifact Registry target.
      image = "${var.vertex_compute_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.mcp_repo.repository_id}/mcp-app:latest"

      ports {
        container_port = 8080
      }
    }
  }

  # Prevent Terraform from resetting active container updates deployed by CI/CD
  lifecycle {
    ignore_changes = [
      template.containers.image
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
