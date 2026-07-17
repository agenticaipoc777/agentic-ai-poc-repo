# ====================================================================
# ELEVATE TF-DEPLOYER TO MANAGE PROJECT POLICIES
# ====================================================================
resource "google_project_iam_member" "tf_deployer_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:tf-deployer@${var.project_id}.iam.gserviceaccount.com"
}
