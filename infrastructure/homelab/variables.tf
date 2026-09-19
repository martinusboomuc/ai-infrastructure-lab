variable "proxmox_endpoint" {
  description = "Proxmox API URL, e.g. https://192.168.1.10:8006"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token in 'user@realm!token-id=uuid' form. Create it under Datacenter > Permissions > API Tokens, scoped to a role that can manage VMs, not the root account's password."
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "Skip TLS certificate verification against the Proxmox API. Needed for the default self-signed certificate; set false once a real certificate is in place."
  type        = bool
  default     = true
}

variable "proxmox_node" {
  description = "Name of the Proxmox node these VMs are created on, e.g. 'pve'. Run `pvesh get /nodes` on the host to confirm."
  type        = string
}

variable "proxmox_ssh_username" {
  description = "SSH username the provider uses against the Proxmox node itself (not the guest VMs) for operations the API alone can't do."
  type        = string
  default     = "root"
}

variable "ssh_public_key" {
  description = "Public key installed for the admin account on every VM via cloud-init. Paste the contents of e.g. ~/.ssh/id_ed25519.pub, not the private key."
  type        = string
}

variable "vm_username" {
  description = "Admin username created on every VM via cloud-init."
  type        = string
  default     = "ops"
}

variable "network_bridge" {
  description = "Proxmox network bridge the VMs attach to. See docs/network/network-topology.md — all three sit on the same flat bridge today, no VLAN segmentation yet."
  type        = string
  default     = "vmbr0"
}

variable "ssd_datastore_id" {
  description = "Proxmox storage ID for the SSD-backed pool. VM root disks and cloud-init drives live here (docs/decisions/0002-proxmox-vm-layout.md). Run `pvesm status` on the host to confirm the name."
  type        = string
}

variable "hdd_datastore_id" {
  description = "Proxmox storage ID for the HDD-backed pool. Bulk, non-latency-sensitive data (Prometheus's TSDB) lives here instead of the SSD pool (docs/decisions/0002-proxmox-vm-layout.md). Run `pvesm status` on the host to confirm the name."
  type        = string
}

variable "image_datastore_id" {
  description = "Proxmox storage ID the base cloud image is downloaded into. Must allow ISO content. Proxmox's built-in 'local' storage does by default."
  type        = string
  default     = "local"
}

variable "snippets_datastore_id" {
  description = "Proxmox storage ID the cloud-init user-data snippet is uploaded to. Must allow Snippets content, enabled manually in the storage's content settings — it is not on by default even for 'local'."
  type        = string
  default     = "local"
}

variable "cloud_image_url" {
  description = "URL of the cloud-init-enabled disk image cloned for every VM."
  type        = string
  default     = "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2"
}
