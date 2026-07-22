# ====================================================================
# Central Google Cloud Project API Engine Activation Matrix
# ====================================================================

resource "google_project_service" "services" {
  for_each = toset([
    # --- YOUR ORIGINAL BASE APIS ---
    "cloudfunctions.googleapis.com",
    "bigquery.googleapis.com",
    "storage-component.googleapis.com",
    "storage.googleapis.com",
    "cloudscheduler.googleapis.com",
    "datastore.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "aiplatform.googleapis.com",
    "generativelanguage.googleapis.com",
    "notebooks.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "discoveryengine.googleapis.com",

    # --- 🔍 APPROVED AGENT PLATFORM APIS ---
    "apphub.googleapis.com",          # App Topology / App Hub Mapping
    "apikeys.googleapis.com",         # Cloud API Registry / API Credentials Management
    "iamcredentials.googleapis.com",  # IAM Connectors / Secure Runtime Token Exchanges
    "iap.googleapis.com",             # Identity-Aware Proxy (IAP) Core Framework
    "modelarmor.googleapis.com",      # Model Armor Enterprise Safety Guardrail Engine
    "networksecurity.googleapis.com", # Network Security Framework Boundaries
    "networkservices.googleapis.com", # Network Services Control Planes
    "observability.googleapis.com",   # Multi-Cloud Unified Observability System
    "texttospeech.googleapis.com",    # Cloud Text-to-Speech Vocalization Components
    "securitycenter.googleapis.com"   # Security Command Center UI 
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}
