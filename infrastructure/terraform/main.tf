resource "google_bigquery_dataset" "analytics_v1" {
  dataset_id                 = "analytics_v1"
  friendly_name              = "Analytics Sandbox Warehouse"
  description                = "Version-controlled infrastructure dataset space"
  location                   = var.region
  delete_contents_on_destroy = true 
}
