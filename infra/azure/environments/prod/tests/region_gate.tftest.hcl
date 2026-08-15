mock_provider "azurerm" {}

run "approved_region_can_plan" {
  command = plan

  variables {
    subscription_id                       = "00000000-0000-0000-0000-000000000001"
    tenant_id                             = "00000000-0000-0000-0000-000000000002"
    location                              = "centralindia"
    public_storage_account_name           = "lingosaitestpublic"
    private_storage_account_name          = "lingosaitestprivate"
    container_registry_name               = "lingosaitestregistry"
    key_vault_name                        = "lingosai-test-vault"
    postgres_server_name                  = "lingosai-test-postgres"
    postgres_administrator_object_id      = "00000000-0000-0000-0000-000000000003"
    postgres_administrator_principal_name = "approved-test-group"
    vm_admin_ssh_public_key               = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN8tRLk6JyKepJj5uX0GzirRq7z2cEk/HsXiAfM1gASw TerraformTestOnly"
    admin_ssh_source_cidr                 = "203.0.113.10/32"
    budget_alert_email                    = "owner@example.com"
    budget_start_date                     = "2026-08-01T00:00:00Z"
  }
}

run "unapproved_region_blocks_plan" {
  command = plan

  variables {
    subscription_id                       = "00000000-0000-0000-0000-000000000001"
    tenant_id                             = "00000000-0000-0000-0000-000000000002"
    location                              = "eastus"
    public_storage_account_name           = "lingosaitestpublic"
    private_storage_account_name          = "lingosaitestprivate"
    container_registry_name               = "lingosaitestregistry"
    key_vault_name                        = "lingosai-test-vault"
    postgres_server_name                  = "lingosai-test-postgres"
    postgres_administrator_object_id      = "00000000-0000-0000-0000-000000000003"
    postgres_administrator_principal_name = "approved-test-group"
    vm_admin_ssh_public_key               = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN8tRLk6JyKepJj5uX0GzirRq7z2cEk/HsXiAfM1gASw TerraformTestOnly"
    admin_ssh_source_cidr                 = "203.0.113.10/32"
    budget_alert_email                    = "owner@example.com"
    budget_start_date                     = "2026-08-01T00:00:00Z"
  }

  expect_failures = [
    check.approved_location,
    azurerm_resource_group.production,
  ]
}
