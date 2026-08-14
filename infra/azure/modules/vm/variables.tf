variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "network_interface_id" {
  type = string
}

variable "admin_username" {
  type = string
}

variable "admin_ssh_public_key" {
  type      = string
  sensitive = true

  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+(?: .*)?$", var.admin_ssh_public_key))
    error_message = "Only an OpenSSH public key is accepted; never provide a private key."
  }
}

variable "vm_size" {
  type = string

  validation {
    condition     = var.vm_size == "Standard_B2ats_v2"
    error_message = "Only the eligible Standard_B2ats_v2 VM is permitted."
  }
}

variable "os_disk_type" {
  type = string

  validation {
    condition     = var.os_disk_type == "Premium_LRS"
    error_message = "The OS disk must be Premium LRS (P6 at 64 GiB)."
  }
}

variable "os_disk_size_gb" {
  type = number

  validation {
    condition     = var.os_disk_size_gb == 64
    error_message = "The topology permits exactly one 64 GiB P6 OS disk."
  }
}

variable "application_worker_count" {
  type = number

  validation {
    condition     = var.application_worker_count == 1
    error_message = "The zero-cost VM permits exactly one application worker."
  }
}

variable "tags" {
  type = map(string)
}
