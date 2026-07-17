# ====================================================================
# 1. CORE APIS FOR ADK AGENTS & AGENT ENGINE
# ====================================================================
resource "google_project_service" "agent_apis" {
  for_each = toset([
    "://googleapis.com", # Core Vertex AI & Reasoning Engine Runtime
    "://googleapis.com", # Grants Gemini API execution privileges
    "://googleapis.com", # Required to hold staged python zipped agent bundles
    "://googleapis.com"  # Enables custom runtime service identity provisioning
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ====================================================================
# 2. ISOLATED DEPLOYMENT STAGING BUCKET
# ====================================================================
resource "google_storage_bucket" "adk_staging" {
  project       = var.project_id
  name          = "${var.project_id}-eu-adk-staging-bucket"
  location      = var.region # Dynamically reads multi-region "EU" from variables.tf
  force_destroy = true

  uniform_bucket_level_access = true

  depends_on = [google_project_service.agent_apis]
}

# ====================================================================
# 3. CUSTOM SERVICE ACCOUNT (THE AGENT IDENTITY)
# ====================================================================
resource "google_service_account" "adk_agent_runner" {
  project      = var.project_id
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Engine Execution Identity"
}

# Role 1: Give the runner account permission to use Vertex AI models
resource "google_project_iam_member" "agent_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 2: Allow the agent to interact with your BigQuery datasets (like analytics_v3)
resource "google_project_iam_member" "agent_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}

# Role 3: Essential Agent Engine background metadata inspection permission 
resource "google_project_iam_member" "agent_metadata_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.adk_agent_runner.email}"
}
