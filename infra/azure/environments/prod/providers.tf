provider "azurerm" {
  features {}

  subscription_id     = var.subscription_id
  tenant_id           = var.tenant_id
  storage_use_azuread = true
}
