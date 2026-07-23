# 1. READ the existing Artifact Registry repository (Prevents 409 Duplicate Errors in CI/CD)
data "google_artifact_registry_repository" "app_repo" {
  location      = "europe-west1"
  repository_id = "streamlit-apps"
}
 
# 2. READ the existing serverless Cloud Run container service (Prevents 409 Duplication Errors)
data "google_cloud_run_v2_service" "streamlit_service" {
  name     = "bq-analytics-frontend"
  location = "europe-west1"
}
 
# 3. Securely bind public view access to the existing Streamlit UI web address
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  # FIXED: Updated references to point to data source variables
  name     = data.google_cloud_run_v2_service.streamlit_service.name
  location = data.google_cloud_run_v2_service.streamlit_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
 
# 4. CRITICAL IAM: Grant Vertex AI User permissions to your Agent Service Account
resource "google_project_iam_member" "vertex_access" {
  project = "agentic-ai-502518"
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-661224241135@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}
