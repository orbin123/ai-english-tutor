variable "subscription_id" {
  description = "Approved Azure subscription ID, supplied out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an approved UUID supplied out of band."
  }
}

variable "tenant_id" {
  description = "Approved Entra tenant ID, supplied out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.tenant_id))
    error_message = "tenant_id must be an approved UUID supplied out of band."
  }
}

variable "location" {
  description = "Exact owner-approved Azure region; currently Central India."
  type        = string
  nullable    = false
}

variable "resource_group_name" {
  description = "Approved bootstrap resource-group name."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^rg-[a-z0-9-]{3,70}$", var.resource_group_name))
    error_message = "resource_group_name must use the reviewed rg-* naming form."
  }
}

variable "storage_account_name" {
  description = "Globally unique state account name; never use an account key."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "storage_account_name must be 3-24 lowercase alphanumeric characters."
  }
}

variable "container_name" {
  description = "Private Terraform state container name."
  type        = string
  default     = "tfstate"

  validation {
    condition     = var.container_name == "tfstate"
    error_message = "The bootstrap root permits exactly the private tfstate container."
  }
}

variable "state_administrator_principal_id" {
  description = "Approved Entra object ID receiving state-container data access."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.state_administrator_principal_id))
    error_message = "state_administrator_principal_id must be an approved UUID."
  }
}

variable "tags" {
  description = "Non-secret ownership and expiry tags."
  type        = map(string)
  default = {
    application = "lingosai"
    environment = "bootstrap"
    managed_by  = "terraform"
    cost_model  = "azure-free-tier"
    expires_on  = "2027-06-18"
  }
}
