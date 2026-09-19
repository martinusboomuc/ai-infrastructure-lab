output "vm_ids" {
  description = "Proxmox VM ID assigned to each VM."
  value       = { for name, vm in proxmox_virtual_environment_vm.this : name => vm.vm_id }
}

output "vm_ipv4_addresses" {
  description = "IPv4 addresses reported by the QEMU guest agent. Empty immediately after apply — the agent needs the VM to finish booting and cloud-init to install it first; re-run `terraform refresh` after a minute or two."
  value       = { for name, vm in proxmox_virtual_environment_vm.this : name => vm.ipv4_addresses }
}
