variable "name" {
  description = "Prefix for every resource (queues become <name>-notifications, ...)."
  type        = string
  default     = "lms"
}

variable "region" {
  description = "Same region as the Neon database (Singapore)."
  type        = string
  default     = "ap-southeast-1"
}

variable "public_url" {
  description = "Where people open the app, e.g. https://learn.example.com"
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate for HTTPS on the load balancer. Empty = HTTP only (testing)."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Image tag in ECR to run (the deploy workflow sets the git SHA)."
  type        = string
  default     = "latest"
}

variable "secrets_arn" {
  description = <<-EOT
    Secrets Manager secret (JSON) with: LMS_DATABASE_URL (Neon pooled URL), LMS_JWT_SECRET,
    LMS_GROQ_API_KEY, LMS_REDIS_URL (Upstash, for rate limits and locks). Created outside Terraform
    so no secret ever sits in state.
  EOT
  type        = string
}

variable "ai_provider" {
  type    = string
  default = "groq"
}

variable "timezone" {
  type    = string
  default = "Asia/Kolkata"
}

# ---- capacity and scaling ---------------------------------------------------------------------
variable "base_instance_type" {
  description = "On-demand floor (ARM/Graviton). Runs the base API tasks."
  type        = string
  default     = "t4g.medium"
}

variable "spot_instance_types" {
  description = "Spot pool for workers and extra API tasks; several types keep Spot available."
  type        = list(string)
  default     = ["t4g.medium", "t4g.large", "m7g.medium", "c7g.large", "m6g.large"]
}

variable "spot_max_instances" {
  type    = number
  default = 6
}

variable "api_min_tasks" {
  type    = number
  default = 2
}

variable "api_max_tasks" {
  type    = number
  default = 8
}

variable "worker_min_tasks" {
  type    = number
  default = 1
}

variable "worker_max_tasks" {
  type    = number
  default = 10
}

variable "worker_concurrency" {
  description = "Jobs one worker runs at a time per queue."
  type        = number
  default     = 8
}

variable "backlog_per_worker" {
  description = "Add a worker for every this many waiting messages."
  type        = number
  default     = 100
}

variable "alarm_email" {
  description = "Gets dead-letter and health alarms. Empty = no email subscription."
  type        = string
  default     = ""
}
