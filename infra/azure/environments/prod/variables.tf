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
  description = "Production resource-group name."
  type        = string
  default     = "rg-lingosai-prod"

  validation {
    condition     = var.resource_group_name == "rg-lingosai-prod"
    error_message = "Exactly one production resource group named rg-lingosai-prod is allowed."
  }
}

variable "public_storage_account_name" {
  description = "Globally unique public-media account name, approved out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.public_storage_account_name))
    error_message = "public_storage_account_name must be 3-24 lowercase alphanumeric characters."
  }
}

variable "private_storage_account_name" {
  description = "Globally unique learner/internal account name, approved out of band."
  type        = string
  nullable    = false

  validation {
    condition = (
      can(regex("^[a-z0-9]{3,24}$", var.private_storage_account_name)) &&
      var.private_storage_account_name != var.public_storage_account_name
    )
    error_message = "private_storage_account_name must be valid and distinct from public storage."
  }
}

variable "container_registry_name" {
  description = "Globally unique ACR name, approved out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-zA-Z0-9]{5,50}$", var.container_registry_name))
    error_message = "container_registry_name must be 5-50 alphanumeric characters."
  }
}

variable "key_vault_name" {
  description = "Globally unique Key Vault name, approved out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{1,22}[a-zA-Z0-9]$", var.key_vault_name))
    error_message = "key_vault_name must satisfy Azure's 3-24 character naming rules."
  }
}

variable "postgres_server_name" {
  description = "Globally unique PostgreSQL Flexible Server name."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.postgres_server_name))
    error_message = "postgres_server_name must be 3-63 lowercase DNS-safe characters."
  }
}

variable "postgres_administrator_object_id" {
  description = "Approved Entra database-administrator group object ID."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.postgres_administrator_object_id))
    error_message = "postgres_administrator_object_id must be an approved UUID."
  }
}

variable "postgres_administrator_principal_name" {
  description = "Display name of the approved Entra database-administrator group."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.postgres_administrator_principal_name)) >= 3
    error_message = "postgres_administrator_principal_name must identify the approved group."
  }
}

variable "vm_admin_username" {
  description = "Non-secret Linux administrator username."
  type        = string
  default     = "azureadmin"

  validation {
    condition     = var.vm_admin_username == "azureadmin"
    error_message = "The reviewed image configuration uses azureadmin."
  }
}

variable "vm_admin_ssh_public_key" {
  description = "Approved SSH public key; never provide a private key."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+(?: .*)?$", var.vm_admin_ssh_public_key))
    error_message = "vm_admin_ssh_public_key must be an OpenSSH public key."
  }
}

variable "admin_ssh_source_cidr" {
  description = "Administrator's approved current public IPv4 /32."
  type        = string
  nullable    = false

  validation {
    condition = (
      can(cidrnetmask(var.admin_ssh_source_cidr)) &&
      can(regex("/32$", var.admin_ssh_source_cidr)) &&
      var.admin_ssh_source_cidr != "0.0.0.0/0"
    )
    error_message = "admin_ssh_source_cidr must be one approved IPv4 /32, never a broad range."
  }
}

variable "budget_alert_email" {
  description = "Approved human recipient for cost alerts; supplied out of band."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.budget_alert_email))
    error_message = "budget_alert_email must be a valid approved email address."
  }
}

variable "budget_start_date" {
  description = "Approved first day of the current UTC budget month."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^20[0-9]{2}-[0-9]{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "budget_start_date must be the first day of an approved UTC month."
  }
}

variable "tags" {
  description = "Additional non-secret tags."
  type        = map(string)
  default     = {}
}
