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

# =======================================================================================================================================================
# 3. DYNAMICALLY FETCH ACTIVE GCP PROJECT METADATA, grantinf acess to SA serviceAccount:service-661224241135@gcp-sa-aiplatform-re.iam.gserviceaccount.com
# ========================================================================================================================================
data "google_project" "current" {
  project_id = var.project_id
}

# ====================================================================
# 4. DEFINE THE GOOGLE-MANAGED VERTEX REASONING ENGINE SERVICE AGENT
# ====================================================================
locals {
  vertex_sa_member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

# ====================================================================
# 5. AUTOMATE BIGQUERY IAM ROLE BINDINGS
# ====================================================================

# Grant dataset discovery and table viewing access
resource "google_project_iam_member" "vertex_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = local.vertex_sa_member
}

# Grant query job execution access
resource "google_project_iam_member" "vertex_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = local.vertex_sa_member
}
