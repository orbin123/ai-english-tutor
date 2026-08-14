output "server_id" {
  value = azurerm_postgresql_flexible_server.production.id
}

output "fqdn" {
  value = azurerm_postgresql_flexible_server.production.fqdn
}
