variable "llm_image_tag" {
  type        = string
  default     = "latest"
  description = "Image tag for the local-llm-chat container. CI/CD overrides this with the commit SHA on each deploy."
}

variable "llm_model_id" {
  type        = string
  default     = "Qwen/Qwen2.5-7B-Instruct"
  description = "Hugging Face model ID baked into the image at build time. Must match the MODEL_ID build-arg used in the Docker build step."
}

variable "llm_use_4bit_quantization" {
  type        = string
  default     = "false"
  description = "Set to \"true\" to load the model in 4-bit quantized mode, letting a larger model fit the same L4 GPU's 24GB VRAM."
}