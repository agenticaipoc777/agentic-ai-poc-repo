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
# 2. UNIFIED RESOURCE GROUP: ALL 5 VIEWER MEMBERS MANAGED IN ONE PLACE
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
