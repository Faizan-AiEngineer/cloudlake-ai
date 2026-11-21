variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "sandbox"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.environment))
    error_message = "Use two to fifteen lowercase letters, digits or hyphens."
  }
}

variable "bucket_name" {
  type        = string
  description = "A globally unique S3 bucket name."
}

variable "enable_schedule" {
  type        = bool
  default     = false
  description = "Enable the daily Glue trigger after a reviewed deployment."
}

variable "enable_arrivals" {
  type        = bool
  default     = false
  description = "Enable landing notifications after all required feeds are staged."
}
