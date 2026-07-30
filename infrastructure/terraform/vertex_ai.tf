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
}


# ====================================================================
# 2. CUSTOM SERVICE ACCOUNT (THE RUNTIME AGENT IDENTITY)
# ====================================================================
resource "google_service_account" "adk_agent_runner" {
  project      = var.project_id
  account_id   = "adk-agent-runner"
  display_name = "ADK Agent Engine Execution Identity"
}


# ====================================================================
# 3. STORAGE ACCESS (SPECIFIC BUCKET-LEVEL BINDING)
# ====================================================================
resource "google_storage_bucket_iam_member" "agent_storage_reader" {
  bucket = google_storage_bucket.adk_staging.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
}


# ====================================================================
# 4. RUNTIME IDENTITY INFRASTRUCTURE BINDINGS
# ====================================================================

# Workload Identity Link: Connects GKE application pods to the service account
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/streamlit-service-account]"
}

# Local Impersonation Link: Allows manual execution using this identity
resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/adk-agent-runner@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "user:lakshmikanth.avh1b@gmail.com"
}


# ====================================================================
# 5. DYNAMIC IAM BINDINGS FOR CORE ADK AGENT RUNNER IDENTITIES
# ====================================================================
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


# ====================================================================
# 6. ENHANCED USER IAM BINDINGS (EXTRACTED FROM THE CONSOLE IMAGE)
# ====================================================================
resource "google_project_iam_member" "user_console_roles" {
  for_each = toset([
    "roles/aiplatform.admin",
    "roles/artifactregistry.writer",
    "roles/bigquery.dataOwner",
    "roles/bigquery.jobUser",
    "roles/notebooks.admin",        # Maps to Notebooks Admin / Cloud NotebookLM Owner scope
    "roles/dialogflow.admin",
    "roles/discoveryengine.admin",
    "roles/cloudaicompanion.admin", # Gemini for Google Cloud Admin
    "roles/owner",
    "roles/billing.projectManager", # Project Billing Manager
    "roles/resourcemanager.projectIamAdmin", # Project IAM Admin
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


# ====================================================================
# 7. ENHANCED TERRAFORM DEPLOYER IAM BINDINGS (EXTRACTED FROM IMAGE)
# ====================================================================
resource "google_project_iam_member" "tf_deployer_roles" {
  for_each = toset([
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin", # Project IAM Admin
    "roles/iam.serviceAccountAdmin",         # Service Account Admin
    "roles/storage.admin"                    # Storage Admin
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:tf-deployer@${var.project_id}.iam.gserviceaccount.com"
}
