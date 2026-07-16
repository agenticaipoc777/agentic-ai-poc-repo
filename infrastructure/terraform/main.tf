# 1. Map the pre-existing analytics_v1 cloud dataset into local state tracking memory
import {
  to = google_bigquery_dataset.analytics_v1
  id = "projects/agentic-ai-502518/datasets/analytics_v1"
}

# 2. Main data warehouse repository layer definition
resource "google_bigquery_dataset" "analytics_v1" {
  dataset_id                 = "analytics_v1" # Fixed: Must match its actual cloud ID
  friendly_name              = "Analytics Sandbox Warehouse"
  description                = "Version-controlled infrastructure dataset space"
  location                   = var.region
  delete_contents_on_destroy = true
}
