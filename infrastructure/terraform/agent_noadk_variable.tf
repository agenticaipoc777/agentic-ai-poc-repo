variable "agent_noadk_image_tag" {
  type        = string
  default     = "latest"
  description = "Image tag for the agent-noadk container. CI/CD overrides this with the commit SHA on each deploy."
}
