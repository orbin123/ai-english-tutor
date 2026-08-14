output "network_interface_id" {
  value = azurerm_network_interface.vm.id
}

output "public_ip_address" {
  value = azurerm_public_ip.vm.ip_address
}
