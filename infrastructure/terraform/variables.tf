variable "project_id" {
  type        = string
  default     = "agentic-ai-502518"
  description = "Your trial BigQuery Project ID"
}

variable "region" {
  type        = string
  default     = "EU"
  description = "Strict data residency multi-region location for data assets"
}

variable "vertex_compute_region" {
  type        = string
  default     = "europe-west1"
  description = "The target regional physical engine endpoint for Vertex AI runtimes"
}

