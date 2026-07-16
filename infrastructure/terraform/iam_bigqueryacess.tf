# 1. First, define the analytics_v3 dataset so it exists in your EU project
resource "google_bigquery_dataset" "analytics_v3" {
  dataset_id                 = "analytics_v3"
  friendly_name              = "Analytics Dataset V3"
  description                = "Isolated dataset layer for external readers"
  location                   = var.region
  delete_contents_on_destroy = true # Safe sandbox override for trial accounts
}

# 2. Assign the BigQuery Data Viewer role on analytics_v3 ONLY
resource "google_bigquery_dataset_iam_member" "svbelose_viewer" {
  dataset_id = google_bigquery_dataset.analytics_v3.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "user:svbelose@gmail.com"
}
