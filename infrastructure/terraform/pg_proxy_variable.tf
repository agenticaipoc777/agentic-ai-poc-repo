variable "pg_proxy_image_tag" {
  type        = string
  default     = "latest"
  description = "Image tag for the bq-pg-proxy container. CI/CD overrides this per-deploy with the commit SHA via -var, so a rollout actually happens on each build instead of Kubernetes seeing an unchanged image reference."
}