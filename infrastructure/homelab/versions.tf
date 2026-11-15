terraform {
  required_version = ">= 1.7"

  # State lives in Azure, not on the Mac that runs Terraform (docs/decisions/0005). The account
  # holds nothing else, keeps every previous version of the state, and the blob lease locks it
  # for the length of each plan or apply. No key here: the backend looks it up through the
  # caller's own `az login`.
  backend "azurerm" {
    resource_group_name  = "homelab-tfstate-rg"
    storage_account_name = "homelabtfstateboom"
    container_name       = "tfstate"
    key                  = "homelab.tfstate"
  }

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.66"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure

  ssh {
    agent    = true
    username = var.proxmox_ssh_username
  }
}
