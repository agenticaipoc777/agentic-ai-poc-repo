# ==============================================================================
# VERTEX AI WORKBENCH INSTANCE FOR ADK AGENT PREDICTIVE PIPELINES
# ==============================================================================
# This resource creates a sandboxed JupyterLab engine configured to natively 
# process your 3-year BigQuery retail dataset with automated cost optimization.

resource "google_workbench_instance" "adk_predictive_workbench" {
  name     = "adk-predictive-analysis-instance" # Unique identifier for the Workbench instance
  location = "europe-west1-b"                   # Targeting Zone B of the Europe West (Belgium) region
  project  = "agentic-ai-502518"                # Your designated Google Cloud Project ID

  # GCE Setup defines the underlying virtual machine compute topology
  gce_setup {
    machine_type = "e2-standard-4" # Provisions 4 vCPUs and 16 GB RAM (Balanced cost/perf ratio)

    # COST OPTIMIZATION: METADATA FOR AUTOMATIC IDLE SHUTDOWN
    # Configures the machine to turn off automatically if left completely inactive.
    # Formula: 10 minutes * 60 seconds = 600 seconds.
    metadata = {
      idle-timeout-seconds = "600"
    }

    # Data Disks section handles the persistent layout for software and metrics files
    data_disks {
      disk_size_gb = 100           # Provisions a 100 GB storage window
      disk_type    = "PD_BALANCED" # Utilizes balanced solid-state (SSD) storage performance
    }

    # Network Interfaces binds the cloud workstation to your secure VPC routing layer
    network_interfaces {
      network = "projects/agentic-ai-502518/global/networks/default"
      subnet  = "projects/agentic-ai-502518/regions/europe-west1/subnetworks/default" # CHANGED FROM subnetwork TO subnet
    }
  }
}
