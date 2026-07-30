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

# NEW: Import for the App Engine default service account shown in your console layout
import {
  to = google_project_iam_member.appengine_default_editor
  id = "agentic-ai-502518/roles/editor/serviceAccount:agentic-ai-502518@appspot.gserviceaccount.com"
}

# NEW: Import tracking block for the explicit terraform deployer pipeline identity
import {
  to = google_service_account.tf_deployer
  id = "projects/agentic-ai-502518/serviceAccounts/tf-deployer@agentic-ai-502518.iam.gserviceaccount.com"
}


# ====================================================================
# 1. PLATFORM RESOURCES: Staging storage and managed runtime identities
# ====================================================================

resource "google_storage_bucket" "adk_staging" {
  project       = var.project_id
  name          = "${var.project_id}-eu-adk-staging-bucket"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}

resource "google_service_account" "adk_agent_runner" {
  project      = var.project_id
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Engine Execution Identity"
}

# Explicit declaration for the pipeline deployment account
resource "google_service_account" "tf_deployer" {
  project      = var.project_id
  account_id   = "tf-deployer"
  display_name = "Terraform Deployer Profile"
}


# ====================================================================
# 2. APP ENGINE DEFAULT CONTEXT
# ====================================================================
resource "google_project_iam_member" "appengine_default_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${var.project_id}@appspot.gserviceaccount.com"
}


# ====================================================================
# 3. RUNTIME LAYER: Specific bucket and structural cluster mappings
# ====================================================================

resource "google_storage_bucket_iam_member" "agent_storage_reader" {
  bucket = google_storage_bucket.adk_staging.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/streamlit-service-account]"
}

resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}


# ====================================================================
# 4. IDENTITY BINDINGS: DYNAMIC PERMISSION MATRICES
# ====================================================================

# Loop A: Project roles assigned directly to your runner identity
resource "google_project_iam_member" "runner_project_roles" {
  for_each = toset([
    "roles/aiplatform.admin",
    "roles/aiplatform.viewer",
    "roles/aiplatform.editor",
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/cloudtrace.agent",
    "roles/dialogflow.admin",
    "roles/discoveryengine.admin",
    "roles/discoveryengine.editor",
    "roles/discoveryengine.serviceAgent",
    "roles/editor",
    "roles/cloudaicompanion.admin",
    "roles/logging.logWriter",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountTokenCreator",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/aiplatform.provisionedThroughputAdmin",
    "roles/aiplatform.serviceAgent",
    "roles/viewer"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
}

# Loop B: Console user access configurations listed in your deployment log
resource "google_project_iam_member" "user_console_roles" {
  for_each = toset([
    "roles/aiplatform.admin",
    "roles/artifactregistry.writer",
    "roles/bigquery.dataOwner",
    "roles/bigquery.jobUser",
    "roles/notebooks.admin",
    "roles/dialogflow.admin",
    "roles/discoveryengine.admin",
    "roles/cloudaicompanion.admin",
    "roles/owner",
    "roles/billing.projectManager",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.serviceAccountUser",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/viewer"
  ])

  project = var.project_id
  role    = each.value
  member  = "user:lakshmikanth.avh1b@gmail.com"
}

# Loop C: Pipeline execution clearance matrix for the tf-deployer account
resource "google_project_iam_member" "deployer_execution_roles" {
  for_each = toset([
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/storage.admin"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:tf-deployer@${var.project_id}.iam.gserviceaccount.com"
}
