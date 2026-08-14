output "public_ip_address" {
  description = "Static VM IPv4 for the later, separately approved DNS cutover."
  value       = module.network.public_ip_address
}

output "vm_principal_id" {
  description = "System-assigned runtime identity for reviewed data-plane grants."
  value       = module.vm.principal_id
}

output "postgres_fqdn" {
  description = "Passwordless PostgreSQL endpoint; no connection secret is emitted."
  value       = module.postgres.fqdn
}

output "blob_account_urls" {
  description = "Credential-free account endpoints for application configuration."
  value = {
    public  = module.storage.public_account_url
    private = module.storage.private_account_url
  }
}

output "container_registry_login_server" {
  description = "ACR endpoint; image publishing belongs to PR 7."
  value       = module.acr.login_server
}

output "key_vault_uri" {
  description = "Vault endpoint; this configuration creates no secrets."
  value       = module.key_vault.vault_uri
}
