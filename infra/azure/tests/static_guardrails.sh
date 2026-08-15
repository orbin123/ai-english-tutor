#!/usr/bin/env bash
set -euo pipefail

azure_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
prod_paths=("$azure_root/environments/prod" "$azure_root/modules")

environment_count="$(find "$azure_root/environments" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
module_count="$(find "$azure_root/modules" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
if [[ "$environment_count" != "1" ]] || [[ ! -d "$azure_root/environments/prod" ]]; then
  printf 'Expected exactly one production environment root.\n' >&2
  exit 1
fi
if [[ "$module_count" != "7" ]]; then
  printf 'Expected exactly seven approved Azure modules, found %s.\n' "$module_count" >&2
  exit 1
fi

count_resources() {
  local pattern="$1"
  rg --glob '*.tf' --count-matches "^resource \"${pattern}\"" "${prod_paths[@]}" \
    | awk -F: '{total += $2} END {print total + 0}'
}

assert_count() {
  local resource_type="$1"
  local expected="$2"
  local actual
  actual="$(count_resources "$resource_type")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'Expected %s %s resource(s), found %s\n' \
      "$expected" "$resource_type" "$actual" >&2
    exit 1
  fi
}

assert_count azurerm_resource_group 1
assert_count azurerm_linux_virtual_machine 1
assert_count azurerm_public_ip 1
assert_count azurerm_network_interface 1
assert_count azurerm_virtual_network 1
assert_count azurerm_subnet 1
assert_count azurerm_network_security_group 1
assert_count azurerm_subnet_network_security_group_association 1
assert_count azurerm_postgresql_flexible_server 1
assert_count azurerm_postgresql_flexible_server_active_directory_administrator 1
assert_count azurerm_postgresql_flexible_server_firewall_rule 1
assert_count azurerm_storage_account 2
assert_count azurerm_storage_container 3
assert_count azurerm_storage_management_policy 2
assert_count azurerm_container_registry 1
assert_count azurerm_key_vault 1
assert_count azurerm_monitor_action_group 1
assert_count azurerm_consumption_budget_resource_group 1
assert_count azurerm_resource_group_policy_assignment 2
assert_count azurerm_role_assignment 4

total_resources="$(rg --glob '*.tf' '^resource "' "${prod_paths[@]}" | wc -l | tr -d ' ')"
if [[ "$total_resources" != "28" ]]; then
  printf 'Expected exactly 28 production Terraform resources, found %s\n' \
    "$total_resources" >&2
  exit 1
fi

bootstrap_resources="$(rg --glob '*.tf' '^resource "' "$azure_root/bootstrap" | wc -l | tr -d ' ')"
if [[ "$bootstrap_resources" != "4" ]]; then
  printf 'Expected exactly four bootstrap resources, found %s\n' \
    "$bootstrap_resources" >&2
  exit 1
fi

bootstrap_paths=("$azure_root/bootstrap")
prod_paths_before_bootstrap=("${prod_paths[@]}")
prod_paths=("${bootstrap_paths[@]}")
assert_count azurerm_resource_group 1
assert_count azurerm_storage_account 1
assert_count azurerm_storage_container 1
assert_count azurerm_role_assignment 1
prod_paths=("${prod_paths_before_bootstrap[@]}")

forbidden_resource_pattern='resource "azurerm_(lb|nat_gateway|bastion_host|vpn_gateway|virtual_network_gateway|private_endpoint|dns_zone|private_dns_zone|frontdoor|application_gateway|static_web_app|log_analytics_workspace|application_insights|security_center_subscription_pricing|marketplace_agreement|redis)"'
if rg --glob '*.tf' "$forbidden_resource_pattern" "${prod_paths[@]}"; then
  printf 'Forbidden Azure service detected.\n' >&2
  exit 1
fi

secret_pattern='administrator_password|client_secret|primary_access_key|secondary_access_key|random_password|azurerm_key_vault_secret'
if rg --glob '*.tf' "$secret_pattern" "$azure_root"; then
  printf 'Secret-bearing Terraform field or resource detected.\n' >&2
  exit 1
fi

if rg --glob '*.tf' 'shared_access_key_enabled[[:space:]]*=[[:space:]]*true' "$azure_root"; then
  printf 'Shared-key authorization must remain disabled.\n' >&2
  exit 1
fi

if rg --glob '*.tf' 'geo_redundant_backup_enabled[[:space:]]*=[[:space:]]*true|auto_grow_enabled[[:space:]]*=[[:space:]]*true|^[[:space:]]*high_availability[[:space:]]*\{' "$azure_root"; then
  printf 'PostgreSQL redundancy or autogrow left the approved disabled state.\n' >&2
  exit 1
fi

approved_region_count="$(rg --glob '*.tf' --count-matches 'approved_locations[[:space:]]*=[[:space:]]*toset\(\["centralindia"\]\)' \
  "$azure_root/bootstrap" "$azure_root/environments/prod" \
  | awk -F: '{total += $2} END {print total + 0}')"
if [[ "$approved_region_count" != "2" ]]; then
  printf 'Both Azure roots must approve exactly Central India.\n' >&2
  exit 1
fi

rg --quiet 'vm_size[[:space:]]*=[[:space:]]*"Standard_B2ats_v2"' \
  "$azure_root/environments/prod/locals.tf"
rg --quiet 'os_disk_size_gb[[:space:]]*=[[:space:]]*64' \
  "$azure_root/environments/prod/locals.tf"
rg --quiet 'postgres_sku[[:space:]]*=[[:space:]]*"B_Standard_B1ms"' \
  "$azure_root/environments/prod/locals.tf"
rg --quiet 'postgres_storage_mb[[:space:]]*=[[:space:]]*32768' \
  "$azure_root/environments/prod/locals.tf"
rg --quiet 'application_worker_count[[:space:]]*=[[:space:]]*1' \
  "$azure_root/environments/prod/locals.tf"
if [[ "$(rg --glob 'providers.tf' --count-matches 'resource_provider_registrations[[:space:]]*=[[:space:]]*"none"' "$azure_root" | awk -F: '{total += $2} END {print total + 0}')" != "2" ]]; then
  printf 'Both Azure roots must keep automatic provider registration disabled.\n' >&2
  exit 1
fi
rg --quiet 'depends_on[[:space:]]*=[[:space:]]*\[module\.cost_guardrails\]' \
  "$azure_root/environments/prod/main.tf"
rg --quiet 'sku[[:space:]]*=[[:space:]]*"Standard"' \
  "$azure_root/modules/acr/main.tf"
rg --quiet 'admin_enabled[[:space:]]*=[[:space:]]*false' \
  "$azure_root/modules/acr/main.tf"
rg --quiet 'sku_name[[:space:]]*=[[:space:]]*"standard"' \
  "$azure_root/modules/key-vault/main.tf"
rg --quiet 'rbac_authorization_enabled[[:space:]]*=[[:space:]]*true' \
  "$azure_root/modules/key-vault/main.tf"
rg --quiet 'container_access_type[[:space:]]*=[[:space:]]*var.public_container_access' \
  "$azure_root/modules/storage/main.tf"
if [[ "$(rg --count-matches 'container_access_type[[:space:]]*=[[:space:]]*var.protected_container_access' "$azure_root/modules/storage/main.tf")" != "2" ]]; then
  printf 'Expected exactly two explicitly protected application containers.\n' >&2
  exit 1
fi
rg --quiet 'amount[[:space:]]*=[[:space:]]*1' \
  "$azure_root/modules/cost-guardrails/main.tf"

printf 'Azure Terraform static guardrails passed.\n'
