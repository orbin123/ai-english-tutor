variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "server_name" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "administrator_object_id" {
  type = string
}

variable "administrator_principal_name" {
  type = string
}

variable "vm_public_ip_address" {
  type = string

  validation {
    condition = (
      can(cidrhost("${var.vm_public_ip_address}/32", 0)) &&
      var.vm_public_ip_address != "0.0.0.0"
    )
    error_message = "PostgreSQL ingress must be the VM's exact nonzero IPv4 address."
  }
}

variable "sku_name" {
  type = string

  validation {
    condition     = var.sku_name == "B_Standard_B1ms"
    error_message = "Only PostgreSQL Flexible Server B_Standard_B1ms is permitted."
  }
}

variable "postgres_version" {
  type = string

  validation {
    condition     = var.postgres_version == "16"
    error_message = "PostgreSQL must remain version 16."
  }
}

variable "storage_mb" {
  type = number

  validation {
    condition     = var.storage_mb == 32768
    error_message = "PostgreSQL storage must be exactly 32 GiB (32768 MiB)."
  }
}

variable "storage_tier" {
  type = string

  validation {
    condition     = var.storage_tier == "P4"
    error_message = "The 32 GiB PostgreSQL allocation must use storage tier P4."
  }
}

variable "backup_retention_days" {
  type = number

  validation {
    condition     = var.backup_retention_days == 7
    error_message = "PostgreSQL backup retention must remain seven days."
  }
}

variable "tags" {
  type = map(string)
}
