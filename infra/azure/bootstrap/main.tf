locals {
  # Approved by the owner after verifying the subscription's free-service
  # meters and both required SKUs in Central India on 15 August 2026.
  approved_locations = toset(["centralindia"])
}

resource "azurerm_resource_group" "state" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags

  lifecycle {
    precondition {
      condition     = contains(local.approved_locations, var.location)
      error_message = "No Azure region is approved. Add exactly one reviewed region before planning."
    }
  }
}

resource "azurerm_storage_account" "state" {
  name                = var.storage_account_name
  resource_group_name = azurerm_resource_group.state.name
  location            = azurerm_resource_group.state.location

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  access_tier              = "Hot"

  https_traffic_only_enabled        = true
  min_tls_version                   = "TLS1_2"
  public_network_access_enabled     = true
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  infrastructure_encryption_enabled = false
  is_hns_enabled                    = false
  nfsv3_enabled                     = false
  sftp_enabled                      = false

  blob_properties {
    change_feed_enabled = false
    versioning_enabled  = false
  }

  tags = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_storage_container" "state" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_role_assignment" "state_administrator" {
  scope                = azurerm_storage_container.state.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = var.state_administrator_principal_id
  principal_type       = "ServicePrincipal"
}
