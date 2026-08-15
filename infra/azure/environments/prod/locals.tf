locals {
  # Approved by the owner after verifying the subscription's free-service
  # meters and both required SKUs in Central India on 15 August 2026.
  approved_locations = toset(["centralindia"])

  vm_size                    = "Standard_B2ats_v2"
  os_disk_type               = "Premium_LRS"
  os_disk_size_gb            = 64
  postgres_sku               = "B_Standard_B1ms"
  postgres_version           = "16"
  postgres_storage_mb        = 32768
  postgres_storage_tier      = "P4"
  postgres_backup_days       = 7
  application_worker_count   = 1
  storage_replication_type   = "LRS"
  public_container_access    = "blob"
  protected_container_access = "private"

  common_tags = merge(var.tags, {
    application = "lingosai"
    environment = "production"
    managed_by  = "terraform"
    cost_model  = "azure-free-tier"
    expires_on  = "2027-06-18"
  })
}

check "approved_location" {
  assert {
    condition = (
      length(local.approved_locations) == 1 &&
      contains(local.approved_locations, var.location)
    )
    error_message = "The requested Azure region is outside the single owner-approved production region."
  }
}

check "zero_cost_topology" {
  assert {
    condition = (
      local.vm_size == "Standard_B2ats_v2" &&
      local.os_disk_type == "Premium_LRS" &&
      local.os_disk_size_gb == 64 &&
      local.postgres_sku == "B_Standard_B1ms" &&
      local.postgres_version == "16" &&
      local.postgres_storage_mb == 32768 &&
      local.postgres_storage_tier == "P4" &&
      local.postgres_backup_days == 7 &&
      local.application_worker_count == 1 &&
      local.storage_replication_type == "LRS" &&
      local.public_container_access == "blob" &&
      local.protected_container_access == "private"
    )
    error_message = "The production topology exceeds or changes the reviewed free-tier envelope."
  }
}
