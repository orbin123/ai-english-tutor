variable "resource_group_id" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "budget_start_date" {
  type = string
}

variable "approved_resource_types" {
  type = list(string)

  validation {
    condition = (
      length(var.approved_resource_types) > 0 &&
      !contains(var.approved_resource_types, "Microsoft.Network/loadBalancers") &&
      !contains(var.approved_resource_types, "Microsoft.Network/natGateways") &&
      !contains(var.approved_resource_types, "Microsoft.Network/privateEndpoints") &&
      !contains(var.approved_resource_types, "Microsoft.OperationalInsights/workspaces") &&
      !contains(var.approved_resource_types, "Microsoft.Insights/components")
    )
    error_message = "The resource allowlist contains a forbidden or cost-expanding service."
  }
}

variable "tags" {
  type = map(string)
}
