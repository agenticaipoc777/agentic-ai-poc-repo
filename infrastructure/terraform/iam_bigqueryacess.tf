# ====================================================================
# 1. DEFINE THE ISOLATED DATASET CONTAINER
# ====================================================================
resource "google_bigquery_dataset" "analytics_v3" {
  dataset_id                 = "analytics_v3"
  friendly_name              = "Analytics Dataset V3"
  description                = "Isolated dataset layer for external readers"
  location                   = var.region
  delete_contents_on_destroy = true

  # Safeguard: Prevents cloud state friction by ignoring external metadata shifts
  lifecycle {
    ignore_changes = [
      access
    ]
  }
}

# ====================================================================
# 2. UNIFIED RESOURCE GROUP: DATA VIEWER MEMBERS
# ====================================================================
resource "google_bigquery_dataset_iam_member" "svbelose_viewer" {
  for_each = toset([
    "dm.maddali@gmail.com",
    "svbelose@gmail.com",
    "Hmmalhotra12@gmail.com",
    "reksaquarian@gmail.com",
    "khushboosamar1989@gmail.com",
    "Iyappan.cpg@gmail.com"
  ])

  dataset_id = google_bigquery_dataset.analytics_v3.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "user:${each.value}"
}

# ====================================================================
# 3. GLOBAL PLATFORM SUPER USER MATRIX FOR LAKSHMIKANTH
# ====================================================================
# This assigns all 14 project-level admin and power-user roles 
# displayed in your screenshot directly to Lakshmi's identity.
resource "google_project_iam_member" "lakshmikanth_super_roles" {
  for_each = toset([
    "roles/aiplatform.admin",                # Agent Platform administrator
    "roles/bigquery.dataOwner",              # BigQuery Data Owner
    "roles/bigquery.jobUser",                # BigQuery Job User
    "roles/notebooks.viewer",                # Cloud Notebooks / NotebookLM User access
    "roles/dialogflow.admin",                # Dialogflow API Admin
    "roles/discoveryengine.admin",           # Discovery Engine Admin
    "roles/cloudaicompanion.admin",          # Gemini for Google Cloud admin
    "roles/billing.projectManager",          # Project Billing Manager
    "roles/resourcemanager.projectIamAdmin", # Project IAM Admin
    "roles/iam.serviceAccountAdmin",         # Service Account Admin
    "roles/iam.serviceAccountTokenCreator",  # Service Account Token Creator
    "roles/iam.serviceAccountUser",          # Service Account User
    "roles/serviceusage.serviceUsageAdmin",  # Service Usage Admin
    "roles/storage.admin"                    # Storage Admin
  ])

  project = var.project_id
  role    = each.value
  member  = "user:lakshmikanth.avh1b@gmail.com"
}
