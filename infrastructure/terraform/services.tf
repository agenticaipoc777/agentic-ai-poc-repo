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

    # --- 🔍 ORANGE-MARKED AGENT PLATFORM APIS ADDED BELOW ---
    "apphub.googleapis.com",                # Topology / App Hub mapping
    "apikeys.googleapis.com",               # Cloud API Registry / Keys
    "iamcredentials.googleapis.com",        # IAM Connectors / Token exchanges
    "iap.googleapis.com",                   # Cloud Identity-Aware Proxy (IAP)
    "modelarmor.googleapis.com",            # Model Armor safety firewall layers
    "networksecurity.googleapis.com",       # Network Security configurations
    "networkservices.googleapis.com",       # Network Services routing fabrics
    "observability.googleapis.com",         # Cloud Observability / Trace frameworks
    "lifesciences.googleapis.com",          # App Lifecycle Manager backbone dependencies
    "securitycommandcenter.googleapis.com", # Security Command Center (SCC) auditing
    "texttospeech.googleapis.com"           # Cloud Text-to-Speech vocalization integrations
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}
