variable "project_id" {
  type = string
}

variable "project_name" {
  type    = string
  default = "pdlcflow"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "db_name" {
  type    = string
  default = "pdlc"
}

variable "db_username" {
  type    = string
  default = "postgres"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_tier" {
  type    = string
  default = "db-custom-2-7680"
}

variable "redis_memory_gb" {
  type    = number
  default = 1
}

variable "api_image" {
  type    = string
  default = "ghcr.io/pdlc-os/pdlcflow-api:latest"
}

variable "api_cpu" {
  type    = string
  default = "1"
}

variable "api_memory" {
  type    = string
  default = "1Gi"
}

variable "app_env" {
  type    = map(string)
  default = {}
}

variable "labels" {
  type    = map(string)
  default = {}
}
