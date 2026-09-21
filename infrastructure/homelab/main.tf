# Provisions the three VMs decided in docs/decisions/0002-proxmox-vm-layout.md. Sizing, disk
# placement (SSD vs HDD) and the deliberate absence of a fourth VM all come from that ADR — a
# change here that adds a VM or reshapes the RAM split contradicts it and should update the ADR
# first, not route around it (see that ADR's Consequences).
#
# Run by hand from a shell with `terraform` installed and a terraform.tfvars filled in (copy
# terraform.tfvars.example). Not run by Claude — this creates real VMs on real hardware. See
# README.md in this directory before the first apply.

locals {
  vms = {
    k8s-01 = {
      vm_id        = 8001
      description  = "Single-node k3s control-plane + worker (docs/decisions/0002-proxmox-vm-layout.md)"
      cpu_cores    = 2
      memory_mb    = 4096
      disk_gb      = 60
      extra_disks  = []
    }
    docker-01 = {
      vm_id       = 8002
      description = "Plain Docker/Compose host, also runs self-hosted MLflow (docs/decisions/0002-proxmox-vm-layout.md, mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md)"
      cpu_cores   = 2
      memory_mb   = 4096
      disk_gb     = 40
      extra_disks = []
    }
    monitoring-01 = {
      vm_id       = 8003
      description = "Prometheus + Grafana (docs/decisions/0002-proxmox-vm-layout.md)"
      cpu_cores   = 1
      memory_mb   = 2048
      disk_gb     = 20
      # Prometheus's TSDB is bulky and not latency-sensitive — ADR-0002 puts it on the HDD pool
      # rather than growing the SSD-backed root disk. 30 GB is a starting point, not a decided
      # budget; resize once real retention numbers exist.
      extra_disks = [
        { datastore_id = var.hdd_datastore_id, size_gb = 30 }
      ]
    }
  }
}

resource "proxmox_virtual_environment_download_file" "cloud_image" {
  content_type = "iso"
  datastore_id = var.image_datastore_id
  node_name    = var.proxmox_node
  url          = var.cloud_image_url

  # Proxmox's content-type check keys off the extension, not the actual file format — naming it
  # .img instead of .qcow2 is what lets a qcow2 downloaded under the ISO content type still be
  # referenced as a disk image's file_id below. Proxmox detects the real format at import time.
  file_name = "debian-12-generic-amd64.img"
}

resource "proxmox_virtual_environment_file" "cloud_init_user_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node

  source_raw {
    data      = file("${path.module}/cloud-init/common-user-data.yaml")
    file_name = "homelab-common-user-data.yaml"
  }
}

resource "proxmox_virtual_environment_vm" "this" {
  for_each = local.vms

  name        = each.key
  description = each.value.description
  node_name   = var.proxmox_node
  vm_id       = each.value.vm_id
  tags        = ["terraform", "homelab"]

  cpu {
    cores = each.value.cpu_cores
    # An early guest kernel panic ("Attempted to kill init!") on this hardware was first thought
    # to be a CPU-type issue and "fixed" by switching to kvm64 — but the panic happened
    # identically under kvm64 and host alike, and the real cause turned out to be the Proxmox
    # host's CPU power management (see docs/architecture/homelab-architecture.md, Hypervisor
    # section, for the actual fix: a host kernel boot parameter). kvm64's minimal instruction set
    # then broke NumPy ("NumPy was built with baseline optimizations: (X86_V2)") the first time a
    # real Python workload (self-hosted MLflow) ran on one of these VMs. "host" is correct once
    # that host-level fix is in place — do not revert to kvm64 without re-reading that section.
    type = "host"
  }

  memory {
    dedicated = each.value.memory_mb
  }

  agent {
    enabled = true
  }

  operating_system {
    type = "l26"
  }

  disk {
    datastore_id = var.ssd_datastore_id
    file_id      = proxmox_virtual_environment_download_file.cloud_image.id
    interface    = "scsi0"
    size         = each.value.disk_gb
    discard      = "on"
    ssd          = true
  }

  dynamic "disk" {
    for_each = each.value.extra_disks
    content {
      datastore_id = disk.value.datastore_id
      interface    = "scsi${disk.key + 1}"
      size         = disk.value.size_gb
      discard      = "on"
    }
  }

  network_device {
    bridge = var.network_bridge
  }

  initialization {
    datastore_id = var.ssd_datastore_id
    # vendor-data layers additively on top of Proxmox's own generated user-data (hostname,
    # ciuser, sshkeys below) — user_data_file_id would replace that generated content outright,
    # which is what silently dropped hostname/user provisioning the first time this was built.
    vendor_data_file_id = proxmox_virtual_environment_file.cloud_init_user_data.id

    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      username = var.vm_username
      keys     = [var.ssh_public_key]
    }
  }
}
