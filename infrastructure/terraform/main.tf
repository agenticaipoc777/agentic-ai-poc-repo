# ====================================================================
# CONFIGURATION MEMORY MANAGEMENT
# ====================================================================

# Automatically maps the pre-existing analytics_v3 dataset into the runner's
# active memory state so it stops trying to recreate a duplicate copy.
import {
  to = google_bigquery_dataset.analytics_v3
  id = "projects/agentic-ai-502518/datasets/analytics_v3"
}

# (The analytics_v1 dataset block has been successfully deleted from here)

