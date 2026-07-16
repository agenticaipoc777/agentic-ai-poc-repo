resource "google_bigquery_table" "stg_github_metadata" {
  dataset_id          = google_bigquery_dataset.analytics_v1.dataset_id
  table_id            = "stg_github_metadata"
  deletion_protection = false # Disables delete blocks so your sandbox runs smoothly

  schema = <<EOF
[
  {
    "name": "execution_time",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Timestamp indicating data ingestion runs"
  },
  {
    "name": "repository_name",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "deployment_status",
    "type": "STRING",
    "mode": "NULLABLE"
  }
]
EOF
}
