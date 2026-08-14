variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "admin_ssh_source_cidr" {
  type = string

  validation {
    condition = (
      can(cidrnetmask(var.admin_ssh_source_cidr)) &&
      can(regex("/32$", var.admin_ssh_source_cidr)) &&
      var.admin_ssh_source_cidr != "0.0.0.0/0"
    )
    error_message = "SSH ingress must be restricted to one approved IPv4 /32."
  }
}

variable "tags" {
  type = map(string)
}
