# Homelab Proxmox provisioning

Terraform for the three VMs decided in
[`docs/decisions/0002-proxmox-vm-layout.md`](../../docs/decisions/0002-proxmox-vm-layout.md):
`k8s-01`, `docker-01` and `monitoring-01`. Provider is
[`bpg/proxmox`](https://registry.terraform.io/providers/bpg/proxmox/latest/docs).

Run this by hand, from a shell with `terraform` installed and network access to the Proxmox
host. Not run by Claude — this creates real VMs on real hardware, and this repository's
convention (root `CLAUDE.md`) is that infrastructure changes are run by the repository owner,
not on his behalf.

## What this does not do

- Does not configure VLAN segmentation — `docs/network/network-topology.md` leaves that open;
  all three VMs land on one flat bridge.
- Does not install Kubernetes, Docker, Prometheus/Grafana or MLflow *inside* the VMs. This module
  stops at a booted VM reachable over SSH with the guest agent running. Provisioning what runs on
  top is separate work (Ansible, or a follow-up module), not yet written.
- Does not manage DNS, TLS, or the Cloudflare Tunnel ADR-0013 calls for on `docker-01` — that's
  configuration inside the VM, not a Proxmox-level resource.

## Prerequisites on the Proxmox host itself

None of these are things Terraform can do for you — they're one-time setup on the host.

1. **An API token**, not the root password. Datacenter > Permissions > API Tokens. Give it a
   role that can manage VMs (`PVEVMAdmin` or similar) rather than reusing an administrator
   token meant for something else.
2. **A storage pool that allows Snippets content**, for the cloud-init user-data file this module
   uploads. Not on by default even for `local` — Datacenter > Storage > (your storage) > Edit >
   Content, tick "Snippets".
3. **Confirm your actual storage IDs** with `pvesm status` on the host. `terraform.tfvars.example`
   assumes `local-lvm` (SSD) and `local-hdd` (HDD); override if yours differ.
4. **Confirm the node name** with `pvesh get /nodes` if it isn't the default `pve`.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with real values from the steps above

terraform init
terraform plan
terraform apply
```

`vm_ipv4_addresses` in the output is empty immediately after apply — the guest agent needs the
VM to finish booting and cloud-init to install it first. Run `terraform refresh` a minute or two
later, or check the Proxmox web UI.

## Tearing down

```bash
terraform destroy
```

Destroys exactly the three VMs this module created — it has no reach outside its own state file.
