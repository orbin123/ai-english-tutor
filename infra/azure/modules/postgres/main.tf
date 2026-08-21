resource "azurerm_postgresql_flexible_server" "production" {
  name                = var.server_name
  resource_group_name = var.resource_group_name
  location            = var.location

  version      = var.postgres_version
  sku_name     = var.sku_name
  storage_mb   = var.storage_mb
  storage_tier = var.storage_tier

  auto_grow_enabled             = false
  backup_retention_days         = var.backup_retention_days
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = var.tenant_id
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags

  lifecycle {
    prevent_destroy = true
    # Azure selects an available zone when none is requested. Preserve that
    # service-assigned placement on later plans instead of trying to clear or
    # relocate the production server.
    ignore_changes = [zone]

    precondition {
      condition = (
        var.sku_name == "B_Standard_B1ms" &&
        var.postgres_version == "16" &&
        var.storage_mb == 32768 &&
        var.storage_tier == "P4" &&
        var.backup_retention_days == 7
      )
      error_message = "PostgreSQL SKU, version, storage, or retention left the approved envelope."
    }
  }
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "approved_group" {
  resource_group_name = var.resource_group_name
  server_name         = azurerm_postgresql_flexible_server.production.name
  tenant_id           = var.tenant_id
  object_id           = var.administrator_object_id
  principal_name      = var.administrator_principal_name
  principal_type      = "Group"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "vm_only" {
  name             = "allow-vm-only"
  server_id        = azurerm_postgresql_flexible_server.production.id
  start_ip_address = var.vm_public_ip_address
  end_ip_address   = var.vm_public_ip_address

  lifecycle {
    precondition {
      condition = (
        var.vm_public_ip_address != "0.0.0.0" &&
        var.vm_public_ip_address != "255.255.255.255"
      )
      error_message = "Broad PostgreSQL firewall ranges and Allow Azure Services are forbidden."
    }
  }
}
