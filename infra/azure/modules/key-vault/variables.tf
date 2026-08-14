variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "key_vault_name" {
  type = string
}

variable "vm_principal_id" {
  type = string
}

variable "tags" {
  type = map(string)
}
