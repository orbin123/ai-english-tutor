variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "public_account_name" {
  type = string
}

variable "private_account_name" {
  type = string

  validation {
    condition     = var.private_account_name != var.public_account_name
    error_message = "Public and protected data must use separate storage accounts."
  }
}

variable "replication_type" {
  type = string

  validation {
    condition     = var.replication_type == "LRS"
    error_message = "Only locally redundant Blob storage is permitted."
  }
}

variable "public_container_access" {
  type = string

  validation {
    condition     = var.public_container_access == "blob"
    error_message = "Public media permits direct blob reads only, never container listing."
  }
}

variable "protected_container_access" {
  type = string

  validation {
    condition     = var.protected_container_access == "private"
    error_message = "Learner and internal data containers must remain private."
  }
}

variable "vm_principal_id" {
  type = string
}

variable "tags" {
  type = map(string)
}
