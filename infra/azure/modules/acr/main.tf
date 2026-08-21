resource "azurerm_container_registry" "production" {
  name                = var.registry_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Standard"
  admin_enabled       = false

  public_network_access_enabled = true
  quarantine_policy_enabled     = false
  zone_redundancy_enabled       = false
  anonymous_pull_enabled        = false
  data_endpoint_enabled         = false

  # Azure permits disabling exports only on Premium ACR. Leave the Standard
  # registry's export policy at its service default to preserve the reviewed
  # zero-cost SKU; image publishing and pulling remain controlled by RBAC.

  tags = var.tags
}

resource "azurerm_role_assignment" "vm_pull" {
  scope                = azurerm_container_registry.production.id
  role_definition_name = "AcrPull"
  principal_id         = var.vm_principal_id
  principal_type       = "ServicePrincipal"
}
