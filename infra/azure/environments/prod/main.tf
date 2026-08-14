resource "azurerm_resource_group" "production" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags

  lifecycle {
    precondition {
      condition = (
        length(local.approved_locations) == 1 &&
        contains(local.approved_locations, var.location)
      )
      error_message = "No Azure region is approved; production planning is blocked."
    }
  }
}

module "network" {
  source = "../../modules/network"

  resource_group_name   = azurerm_resource_group.production.name
  location              = azurerm_resource_group.production.location
  admin_ssh_source_cidr = var.admin_ssh_source_cidr
  tags                  = local.common_tags
}

module "vm" {
  source = "../../modules/vm"

  resource_group_name      = azurerm_resource_group.production.name
  location                 = azurerm_resource_group.production.location
  network_interface_id     = module.network.network_interface_id
  admin_username           = var.vm_admin_username
  admin_ssh_public_key     = var.vm_admin_ssh_public_key
  vm_size                  = local.vm_size
  os_disk_type             = local.os_disk_type
  os_disk_size_gb          = local.os_disk_size_gb
  application_worker_count = local.application_worker_count
  tags                     = local.common_tags
}

module "postgres" {
  source = "../../modules/postgres"

  resource_group_name          = azurerm_resource_group.production.name
  location                     = azurerm_resource_group.production.location
  server_name                  = var.postgres_server_name
  tenant_id                    = var.tenant_id
  administrator_object_id      = var.postgres_administrator_object_id
  administrator_principal_name = var.postgres_administrator_principal_name
  vm_public_ip_address         = module.network.public_ip_address
  sku_name                     = local.postgres_sku
  postgres_version             = local.postgres_version
  storage_mb                   = local.postgres_storage_mb
  storage_tier                 = local.postgres_storage_tier
  backup_retention_days        = local.postgres_backup_days
  tags                         = local.common_tags
}

module "storage" {
  source = "../../modules/storage"

  resource_group_name        = azurerm_resource_group.production.name
  location                   = azurerm_resource_group.production.location
  public_account_name        = var.public_storage_account_name
  private_account_name       = var.private_storage_account_name
  replication_type           = local.storage_replication_type
  public_container_access    = local.public_container_access
  protected_container_access = local.protected_container_access
  vm_principal_id            = module.vm.principal_id
  tags                       = local.common_tags
}

module "acr" {
  source = "../../modules/acr"

  resource_group_name = azurerm_resource_group.production.name
  location            = azurerm_resource_group.production.location
  registry_name       = var.container_registry_name
  vm_principal_id     = module.vm.principal_id
  tags                = local.common_tags
}

module "key_vault" {
  source = "../../modules/key-vault"

  resource_group_name = azurerm_resource_group.production.name
  location            = azurerm_resource_group.production.location
  tenant_id           = var.tenant_id
  key_vault_name      = var.key_vault_name
  vm_principal_id     = module.vm.principal_id
  tags                = local.common_tags
}

module "cost_guardrails" {
  source = "../../modules/cost-guardrails"

  resource_group_id   = azurerm_resource_group.production.id
  resource_group_name = azurerm_resource_group.production.name
  location            = azurerm_resource_group.production.location
  alert_email         = var.budget_alert_email
  budget_start_date   = var.budget_start_date
  approved_resource_types = [
    "Microsoft.Authorization/policyAssignments",
    "Microsoft.Authorization/roleAssignments",
    "Microsoft.Compute/disks",
    "Microsoft.Compute/virtualMachines",
    "Microsoft.Consumption/budgets",
    "Microsoft.ContainerRegistry/registries",
    "Microsoft.DBforPostgreSQL/flexibleServers",
    "Microsoft.DBforPostgreSQL/flexibleServers/administrators",
    "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules",
    "Microsoft.Insights/actionGroups",
    "Microsoft.KeyVault/vaults",
    "Microsoft.Network/networkInterfaces",
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Network/publicIPAddresses",
    "Microsoft.Network/virtualNetworks",
    "Microsoft.Network/virtualNetworks/subnets",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Storage/storageAccounts/blobServices/containers",
    "Microsoft.Storage/storageAccounts/managementPolicies",
  ]
  tags = local.common_tags
}
