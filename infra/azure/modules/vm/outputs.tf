output "principal_id" {
  value = azurerm_linux_virtual_machine.application.identity[0].principal_id
}

output "virtual_machine_id" {
  value = azurerm_linux_virtual_machine.application.id
}
