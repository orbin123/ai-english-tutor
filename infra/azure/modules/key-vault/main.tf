resource "azurerm_key_vault" "production" {
  name                = var.key_vault_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled      = true
  enabled_for_deployment          = false
  enabled_for_disk_encryption     = false
  enabled_for_template_deployment = false
  public_network_access_enabled   = true
  purge_protection_enabled        = false
  soft_delete_retention_days      = 7

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_role_assignment" "vm_secret_reader" {
  scope                = azurerm_key_vault.production.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.vm_principal_id
  principal_type       = "ServicePrincipal"
}
