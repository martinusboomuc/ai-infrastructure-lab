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
  stops at a booted VM reachable over SSH with the guest agent running. `k8s-01` has k3s, `docker-01`
  has Docker and MLflow, and `monitoring-01` has Docker, Prometheus and Grafana — all installed by
  hand over SSH (see below), not by this module. Whether any of this moves to Ansible or a
  follow-up module is an open question, not a decision made here.
- Does not manage DNS, TLS, or the Cloudflare Tunnel ADR-0013 calls for on `docker-01` — that's
  configuration inside the VM, not a Proxmox-level resource.

## Prerequisites on the Proxmox host itself

None of these are things Terraform can do for you — they're one-time setup on the host.

1. **An API token**, not the root password. Datacenter > Permissions > API Tokens. Give it a
   role that can manage VMs (`PVEVMAdmin` or similar) rather than reusing an administrator
   token meant for something else.
2. **A storage pool that allows Snippets content**, for the cloud-init vendor-data file this
   module uploads. Not on by default even for `local` — Datacenter > Storage > (your storage) >
   Edit > Content, tick "Snippets".
3. **Confirm your actual storage IDs** with `pvesm status` on the host. `terraform.tfvars.example`
   assumes `local-lvm` (SSD) and `local-hdd` (HDD); override if yours differ.
4. **Confirm the node name** with `pvesh get /nodes` if it isn't the default `pve`.
5. **On this specific hardware, a host kernel boot parameter is required** for VMs to boot under
   KVM at all — see `docs/architecture/homelab-architecture.md`'s Hypervisor section. Without it,
   every VM this module creates kernel-panics seconds into boot. If this Terraform is ever run
   against a different or reinstalled host, check whether the same CPU-family issue applies before
   assuming a fresh crash means something's wrong with the Terraform itself.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with real values from the steps above

terraform init
terraform plan
terraform apply -parallelism=1
```

**Use `-parallelism=1` on `apply`.** All three VMs import their disk from the same source image
onto the same storage; Proxmox holds an exclusive lock during that import, so creating them
concurrently (Terraform's default) causes the later ones to time out waiting for the lock and
fail with a corrupted disk configuration. Sequential creation avoids this entirely, at the cost
of a slower apply (roughly 15 minutes per VM on this hardware).

`vm_ipv4_addresses` in the output is empty immediately after apply — the guest agent needs the
VM to finish booting and cloud-init to install it first. Run `terraform refresh` a minute or two
later, or check the Proxmox web UI. If a VM's console shows a kernel panic instead of a login
prompt, see the boot-parameter prerequisite above — `qm stop`/`qm start` on that one VM is
usually enough to get a clean boot on retry.

## k3s on k8s-01

Installed by hand over SSH, not by Terraform:

```bash
ssh -i ~/.ssh/id_ed25519_ai_lab ops@<k8s-01's IP>
curl -sfL https://get.k3s.io | sh -
```

The default install is a single-node cluster (control-plane and worker combined, per
[ADR-0002](../../docs/decisions/0002-proxmox-vm-layout.md)) with k3s's bundled components:
Traefik ingress, `local-path-provisioner` for storage, CoreDNS, `metrics-server`. No extra install
flags needed for this layout.

To run `kubectl` from the MacBook instead of SSHing in every time:

```bash
mkdir -p ~/.kube
ssh -i ~/.ssh/id_ed25519_ai_lab ops@<k8s-01's IP> "sudo cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/config
sed -i '' 's/127.0.0.1/<k8s-01's IP>/' ~/.kube/config
chmod 600 ~/.kube/config
kubectl get nodes
```

k3s's default kubeconfig points at `127.0.0.1` because it's written to be used from the node
itself — the `sed` rewrite is what makes it usable remotely. The file contains a client
certificate; `chmod 600` and treat it like any other credential, not something to commit.

## MLflow on docker-01

See [`mlflow/README.md`](mlflow/README.md) — a Docker Compose stack for BankML's self-hosted
MLflow tracking server ([ADR-0013](../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md)),
reachable through a Cloudflare Tunnel gated by Access. Artifact storage is still a local Docker
volume, not Azure Blob as that ADR decided.

## Prometheus and Grafana on monitoring-01

See [`monitoring/README.md`](monitoring/README.md) — a Docker Compose stack for Prometheus and
Grafana, scraping `node_exporter` (installed as a systemd service, not a container) on all three
VMs plus the Proxmox host itself, [`cadvisor/`](cadvisor/README.md) for per-container metrics on
`docker-01`, [`k3s/`](k3s/README.md) for pod/deployment-level cluster state on `k8s-01`, and
BankML's deployed serving app directly. Host, container, pod and application metrics are all
covered now; per-service alerting beyond BankML's own drift job is still open.

## Tearing down

```bash
terraform destroy
```

Destroys exactly the three VMs this module created — it has no reach outside its own state file.
