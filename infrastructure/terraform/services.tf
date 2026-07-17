# ============================================================
# Central Google Cloud Project API Engine Activation Matrix
# ============================================================

resource "google_project_service" "services" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "bigquery.googleapis.com",
    "storage-component.googleapis.com", # Handles base GCS storage components
    "storage.googleapis.com",           # Explicit object storage API for bucket staging
    "cloudscheduler.googleapis.com",
    "datastore.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "aiplatform.googleapis.com",         # Core Vertex AI & Reasoning Engine Runtime
    "generativelanguage.googleapis.com", # Grants Gemini API execution privileges
    "notebooks.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com", # Required to provision Custom Service Accounts
    "cloudresourcemanager.googleapis.com",
    "discoveryengine.googleapis.com" # Agent Builder / Enterprise Search Engine capabilities
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}
