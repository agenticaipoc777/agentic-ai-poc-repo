# ====================================================================
# 1. ARTIFACT REGISTRY: Retained to store your Streamlit Docker images
# ====================================================================
resource "google_artifact_registry_repository" "app_repo" {
  project       = "agentic-ai-502518"
  location      = "europe-west1"
  repository_id = "streamlit-apps"
  format        = "DOCKER"
  description   = "Docker repository for Streamlit frontend apps"
}

# ====================================================================
# 2. GKE KUBERNETES CLUSTER: Autopilot engine optimized for cost & scale
# ====================================================================
resource "google_container_cluster" "gke_cluster" {
  name     = "adk-analytics-gke-cluster"
  project  = "agentic-ai-502518"
  location = "europe-west1" # Regional cluster across europe-west1 zones

  # Enable Autopilot for hands-free node, OS, and scaling management
  enable_autopilot = true

  # Connects directly to your default network layout
  network    = "projects/agentic-ai-502518/global/networks/default"
  subnetwork = "projects/agentic-ai-502518/regions/europe-west1/subnetworks/default"

  # IP Allocation policy required for VPC-native routing clusters
  ip_allocation_policy {
    cluster_ipv4_cidr_block  = ""
    services_ipv4_cidr_block = ""
  }
}

# ====================================================================
# 3. WORKLOAD IDENTITY SERVICE ACCOUNT LINK
# ====================================================================
# Grants your active GKE pods authorization to impersonate your adk-agent-runner 
# service account so they can query BigQuery and Vertex AI without keys.
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = "projects/agentic-ai-502518/serviceAccounts/adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:agentic-ai-502518.svc.id.goog[default/streamlit-service-account]"
}

# ====================================================================
# 4. DATASET & CLOUD PLATFORM PERMISSIONS: Retained from Cloud Run
# ====================================================================
resource "google_project_iam_member" "runner_vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}

resource "google_artifact_registry_repository_iam_member" "runner_registry_reader" {
  project    = "agentic-ai-502518"
  location   = google_artifact_registry_repository.app_repo.location
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:adk-agent-runner@agentic-ai-502518.iam.gserviceaccount.com"
}
