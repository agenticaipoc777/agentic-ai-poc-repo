# ====================================================================
# CONFIGURATION MEMORY MANAGEMENT (STATE IMPORTS)
# ====================================================================

# Links the existing Google Cloud Storage bucket into Terraform state memory
import {
  to = google_storage_bucket.adk_staging
  id = "agentic-ai-502518-eu-adk-staging-bucket"
}

# Links the existing custom service account into Terraform state memory
import {
  to = google_service_account.adk_agent_runner
  id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}

# ====================================================================
# 1. ISOLATED EU DEPLOYMENT STAGING BUCKET
# ====================================================================
resource "google_storage_bucket" "adk_staging" {
  project       = var.project_id
  name          = "${var.project_id}-eu-adk-staging-bucket"
  location      = var.region 
  force_destroy = true       

  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.services]
}

# ====================================================================
# 2. CUSTOM SERVICE ACCOUNT (THE RUNTIME AGENT IDENTITY)
# ====================================================================
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

