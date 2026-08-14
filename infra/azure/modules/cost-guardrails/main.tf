locals {
  allowed_locations_policy_id = "/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c"
  allowed_types_policy_id     = "/providers/Microsoft.Authorization/policyDefinitions/a08ec900-254a-4555-9bf5-e42af04b5c5c"
}

resource "azurerm_monitor_action_group" "cost" {
  name                = "ag-lingosai-prod-cost"
  resource_group_name = var.resource_group_name
  short_name          = "cost-alert"
  enabled             = true
  tags                = var.tags

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_consumption_budget_resource_group" "production" {
  name              = "budget-lingosai-prod"
  resource_group_id = var.resource_group_id
  amount            = 1
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
    end_date   = "2027-07-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 25
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost.id]
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost.id]
  }

  notification {
    enabled        = true
    threshold      = 75
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost.id]
  }

  notification {
    enabled        = true
    threshold      = 90
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_groups = [azurerm_monitor_action_group.cost.id]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_groups = [azurerm_monitor_action_group.cost.id]
  }
}

resource "azurerm_resource_group_policy_assignment" "allowed_location" {
  name                 = "deny-unapproved-locations"
  resource_group_id    = var.resource_group_id
  policy_definition_id = local.allowed_locations_policy_id
  enforce              = true
  description          = "Deny resources outside the one owner-approved production region."
  display_name         = "LingosAI: deny unapproved Azure locations"

  parameters = jsonencode({
    listOfAllowedLocations = {
      value = [var.location]
    }
  })

  non_compliance_message {
    content = "The resource location is outside the reviewed zero-cost production region."
  }
}

resource "azurerm_resource_group_policy_assignment" "allowed_resource_types" {
  name                 = "deny-unapproved-types"
  resource_group_id    = var.resource_group_id
  policy_definition_id = local.allowed_types_policy_id
  enforce              = true
  description          = "Deny services outside the reviewed minimal production topology."
  display_name         = "LingosAI: deny unapproved Azure resource types"

  parameters = jsonencode({
    listOfResourceTypesAllowed = {
      value = var.approved_resource_types
    }
  })

  non_compliance_message {
    content = "This resource type is outside the reviewed zero-cost production topology."
  }
}
