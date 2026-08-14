resource "azurerm_storage_account" "public" {
  name                = var.public_account_name
  resource_group_name = var.resource_group_name
  location            = var.location

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = var.replication_type
  access_tier              = "Hot"

  https_traffic_only_enabled        = true
  min_tls_version                   = "TLS1_2"
  public_network_access_enabled     = true
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = true
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

    precondition {
      condition     = var.replication_type == "LRS"
      error_message = "Public media storage must remain Standard Hot LRS."
    }
  }
}

resource "azurerm_storage_account" "private" {
  name                = var.private_account_name
  resource_group_name = var.resource_group_name
  location            = var.location

  account_kind             = "StorageV2"
  account_tier             = "Standard"
  account_replication_type = var.replication_type
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

    precondition {
      condition = (
        var.replication_type == "LRS" &&
        var.private_account_name != var.public_account_name
      )
      error_message = "Protected storage must remain separate Standard Hot LRS."
    }
  }
}

resource "azurerm_storage_container" "public_media" {
  name                  = "public-media"
  storage_account_id    = azurerm_storage_account.public.id
  container_access_type = var.public_container_access

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.public_container_access == "blob"
      error_message = "Public media may allow blob reads but never container listing."
    }
  }
}

resource "azurerm_storage_container" "learner_media" {
  name                  = "learner-media"
  storage_account_id    = azurerm_storage_account.private.id
  container_access_type = var.protected_container_access

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.protected_container_access == "private"
      error_message = "Learner media must never permit anonymous access."
    }
  }
}

resource "azurerm_storage_container" "internal_media" {
  name                  = "internal-media"
  storage_account_id    = azurerm_storage_account.private.id
  container_access_type = var.protected_container_access

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.protected_container_access == "private"
      error_message = "Internal data must never permit anonymous access."
    }
  }
}

resource "azurerm_storage_management_policy" "public" {
  storage_account_id = azurerm_storage_account.public.id

  rule {
    name    = "delete-generated-images-after-7-days"
    enabled = true

    filters {
      prefix_match = ["public-media/images/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }
    }
  }

  rule {
    name    = "delete-tts-cache-after-30-days"
    enabled = true

    filters {
      prefix_match = ["public-media/audio/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 30
      }
    }
  }
}

resource "azurerm_storage_management_policy" "private" {
  storage_account_id = azurerm_storage_account.private.id

  rule {
    name    = "delete-learner-media-after-7-days"
    enabled = true

    filters {
      prefix_match = ["learner-media/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }
    }
  }

  rule {
    name    = "delete-internal-data-after-7-days"
    enabled = true

    filters {
      prefix_match = ["internal-media/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }
    }
  }
}

resource "azurerm_role_assignment" "vm_public_blob_data" {
  scope                = azurerm_storage_account.public.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.vm_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "vm_private_blob_data" {
  scope                = azurerm_storage_account.private.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.vm_principal_id
  principal_type       = "ServicePrincipal"
}
