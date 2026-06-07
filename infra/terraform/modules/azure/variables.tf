variable "project_name" {
  type    = string
  default = "pdlcflow"
}

variable "location" {
  type    = string
  default = "eastus"
}

# Globally unique, 3-24 chars, lowercase alphanumeric.
variable "storage_account_name" {
  type    = string
  default = "pdlcflowstore"
}

variable "db_name" {
  type    = string
  default = "pdlc"
}

variable "db_username" {
  type    = string
  default = "pdlcadmin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_sku" {
  type    = string
  default = "GP_Standard_D2s_v3"
}

variable "api_image" {
  type    = string
  default = "ghcr.io/pdlc-os/pdlcflow-api:latest"
}

variable "api_cpu" {
  type    = number
  default = 0.5
}

variable "api_memory" {
  type    = string
  default = "1Gi"
}

variable "app_env" {
  type    = map(string)
  default = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}
