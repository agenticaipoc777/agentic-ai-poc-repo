# ====================================================================
# 1. ISOLATED DEPLOYMENT STAGING BUCKET
# ====================================================================
# Agent Engine requires a Cloud Storage bucket to temporarily stage 
# your zipped Python agent packages, requirements.txt, and dependencies.
resource "google_storage_bucket" "adk_staging" {
  project       = var.project_id
  name          = "${var.project_id}-eu-adk-staging-bucket" 
  location      = var.region                                # Inherits strict multi-region "EU" configuration
  force_destroy = true                                      # Allows easy automatic cleanup of old deployment artifacts

  uniform_bucket_level_access = true

  # Safety: Prevents resource creation until the core service matrix completes
  depends_on = [google_project_service.services]
}

# ====================================================================
# 2. CUSTOM SERVICE ACCOUNT (THE AGENT RUNTME IDENTITY)
# ====================================================================
# Create a dedicated runner identity for your deployed ADK agents.
# This prevents running live agents under high-privilege default project owners.
resource "google_service_account" "adk_agent_runner" {
  project      = var.project_id
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Engine Execution Identity"

  depends_on = [google_project_service.services]
}

# ====================================================================
# 3. LEAST-PRIVILEGE SECURITY ROLES ATTACHMENT
# ====================================================================

# Role 1: Give the runner identity permission to call Vertex AI models (like Gemini)
resource "google_project_iam_member" "agent_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 2: Allow the agent to interact with and read your analytics_v3 BigQuery dataset
resource "google_project_iam_member" "agent_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 3: Essential Agent Engine background metadata inspection permission 
resource "google_project_iam_member" "agent_metadata_viewer" {
  project = var.project_id
  role    = "roles/viewer" # Required for global platform structural lookups during runtime
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}
