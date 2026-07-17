# ====================================================================
# 1. ISOLATED EU DEPLOYMENT STAGING BUCKET
# ====================================================================
# Agent Engine uses this bucket to temporarily stage your zipped Python 
# agent packages, requirements.txt, and dependency artifacts.
resource "google_storage_bucket" "adk_staging" {
  project       = var.project_id
  name          = "${var.project_id}-eu-adk-staging-bucket"
  location      = var.region # Dynamically inherits your strict multi-region "EU" configuration
  force_destroy = true       # Permits clean, automated deletion of legacy agent staging builds

  uniform_bucket_level_access = true

  # Safety loop dependency guard against your central services matrix
  depends_on = [google_project_service.services]
}

# ====================================================================
# 2. CUSTOM SERVICE ACCOUNT (THE RUNTIME AGENT IDENTITY)
# ====================================================================
# Dedicated execution identity for your deployed ADK agents.
# This prevents running agents under high-privilege default project owners.
resource "google_service_account" "adk_agent_runner" {
  project      = var.project_id
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Engine Execution Identity"

  depends_on = [google_project_service.services]
}

# ====================================================================
# 3. SECURITY ROLES ATTACHMENT FOR THE ADK AGENT IDENTITY
# ====================================================================

# Role 1: Vertex AI computing user privileges to invoke Gemini models
resource "google_project_iam_member" "agent_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 2: Grants read rights to query your analytics_v3 dataset target
resource "google_project_iam_member" "agent_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 3: Metadata retrieval layer for structural project inspections
resource "google_project_iam_member" "agent_metadata_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}
