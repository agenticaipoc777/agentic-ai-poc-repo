# 1. Define the isolated dataset container
resource "google_bigquery_dataset" "analytics_v3" {
  dataset_id                 = "analytics_v3"
  friendly_name              = "Analytics Dataset V3"
  description                = "Isolated dataset layer for external readers"
  location                   = var.region
  delete_contents_on_destroy = true 
}

# 2. Grant the isolated BigQuery Data Viewer role exclusively on analytics_v3
resource "google_bigquery_dataset_iam_member" "svbelose_viewer" {
  dataset_id = google_bigquery_dataset.analytics_v3.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "user:svbelose@gmail.com"
}
