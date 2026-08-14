resource "azurerm_linux_virtual_machine" "application" {
  name                = "vm-lingosai-prod"
  resource_group_name = var.resource_group_name
  location            = var.location
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [var.network_interface_id]

  disable_password_authentication = true
  encryption_at_host_enabled      = false
  secure_boot_enabled             = true
  vtpm_enabled                    = true
  patch_assessment_mode           = "AutomaticByPlatform"
  patch_mode                      = "AutomaticByPlatform"
  provision_vm_agent              = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.admin_ssh_public_key
  }

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    name                 = "disk-lingosai-prod-os"
    caching              = "ReadWrite"
    storage_account_type = var.os_disk_type
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  tags = merge(var.tags, {
    application_workers = tostring(var.application_worker_count)
  })

  lifecycle {
    precondition {
      condition = (
        var.vm_size == "Standard_B2ats_v2" &&
        var.os_disk_type == "Premium_LRS" &&
        var.os_disk_size_gb == 64 &&
        var.application_worker_count == 1
      )
      error_message = "VM size, P6 OS disk, or one-worker topology changed."
    }
  }
}
