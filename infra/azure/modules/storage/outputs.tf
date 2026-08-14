output "public_account_url" {
  value = azurerm_storage_account.public.primary_blob_endpoint
}

output "private_account_url" {
  value = azurerm_storage_account.private.primary_blob_endpoint
}
