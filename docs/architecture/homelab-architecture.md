# Homelab architecture

See [ADR-0001](../decisions/0001-hybrid-infrastructure.md) for the reasoning behind splitting
work this way. This document describes the actual current and planned state; it changes as the
hardware and services change, unlike the ADR which records the decision at a point in time.

## Current hardware

A repurposed desktop, running as the homelab's only machine today:

| Component | Spec |
| --- | --- |
| CPU | Intel Core i5 (5th generation) |
| RAM | 16 GB DDR3 |
| Storage | 512 GB SSD + 1 TB HDD |
| GPU | NVIDIA GTX 1050 Ti |

No RAID, no redundant storage, no backup target beyond the two local disks. Treated as
**temporary** — see "Planned hardware" below. Nothing irreplaceable should be the sole copy on
this machine (this is why BankML's DVC remote stays on Azure Blob Storage rather than moving
here — [ADR-0001](../decisions/0001-hybrid-infrastructure.md)'s Consequences).

## Hypervisor

**Proxmox VE.** Installed and operational: networking configured, internet connectivity
working, managed headless (no monitor/keyboard/mouse needed once booted).

**Required boot parameter.** This CPU hits a reproducible guest kernel panic under KVM
(`Attempted to kill init!`, seconds into boot) without `processor.max_cstate=1
intel_idle.max_cstate=0` on the host's kernel command line — consumer desktop boards' CPU
power-management (deep C-states) isn't validated for the constant VM-exit/VM-entry cycling KVM
does, unlike server-grade hardware. Confirmed the crash disappears entirely under pure software
emulation (`--kvm 0`, no CPU passthrough involved) and is unrelated to guest CPU type (`host` and
`kvm64` both crashed identically) or disk corruption (same disk, no crash without KVM) — isolating
it to KVM's interaction with this host's idle states. Set via `/etc/default/grub`'s
`GRUB_CMDLINE_LINUX_DEFAULT`, applied to **both** `/boot/grub/grub.cfg` and
`/boot/efi/EFI/proxmox/grub.cfg` (this is a UEFI install with two separate grub.cfg files —
`update-grub` alone only regenerates the first; the actual EFI boot needs
`grub-mkconfig -o /boot/efi/EFI/proxmox/grub.cfg` run explicitly too). The mitigation reduces the
crash's probability rather than eliminating it outright — an occasional VM still needs one
`qm stop`/`qm start` retry after a fresh boot. If this host is ever reinstalled, redo this before
concluding VMs are broken.

**Guest CPU type is `host`, not `kvm64`.** `kvm64` was tried as part of diagnosing the panic
above and turned out not to matter (both crashed identically) — the boot parameter was the real
fix. `kvm64` was left in place afterward anyway and later broke NumPy on `docker-01`
(`RuntimeError: NumPy was built with baseline optimizations: (X86_V2) but your machine doesn't
support: (X86_V2)`), since it's QEMU's most conservative CPU model and doesn't expose the
instruction set modern prebuilt Python wheels assume. All three VMs now use `host` — full feature
passthrough, safe now that the actual cause is fixed at the host level.

## Remote management

- **Wake-on-LAN** is configured and working — the machine can be powered on remotely from the
  MacBook.
- Today, remote management happens over the local network.
- **Planned:** external (off-LAN) access via VPN. Management interfaces are deliberately never
  exposed directly to the internet. See
  [network-topology.md](../network/network-topology.md) for what's actually decided about this
  versus still open.

## Role split

| Machine | Role |
| --- | --- |
| MacBook | Development client: VS Code, terminal, Git/GitHub, documentation, remote administration. No infrastructure services, no long-term data. |
| Homelab | Self-hosted infrastructure: Linux VMs, Docker, Kubernetes, Terraform testing, the Prometheus/Grafana monitoring stack, CI/CD experimentation, MLOps services where self-hosting is the more useful thing to learn. |
| Public cloud (Azure now, AWS later) | Managed services where that's the industry-standard solution — e.g. BankML's DVC remote on Azure Blob Storage. |

## VM layout

See [ADR-0002](../decisions/0002-proxmox-vm-layout.md) for the reasoning. Provisioned via
Terraform (`infrastructure/homelab/`) and reachable over SSH as the `ops` user, DHCP-assigned
addresses on the flat LAN:

| VM | Role | RAM | vCPU | Disk | Address (DHCP, may change) |
| --- | --- | --- | --- | --- | --- |
| `k8s-01` | Single-node k3s (control-plane + worker combined) | 4 GB | 2 | 60 GB | 192.168.1.183 |
| `docker-01` | Plain Docker/Compose host for anything outside the cluster | 4 GB | 2 | 40 GB | 192.168.1.115 |
| `monitoring-01` | Prometheus + Grafana | 2 GB | 1 | 20 GB | 192.168.1.136 |

These addresses are DHCP leases, not static reservations — `network-topology.md`'s "What's not
decided yet" already flags IP addressing as an open item. If a lease changes, re-check with
`qm agent <vmid> network-get-interfaces` on the Proxmox host rather than assuming these are
stale; a router-side DHCP reservation per VM's MAC address would make this table permanently
accurate, but that's a decision for `network-topology.md`, not made here.

**`k8s-01` is running k3s** (installed via the upstream install script, not yet via Terraform or
Ansible — see `infrastructure/homelab/README.md` for the exact command and how `kubectl` from
the MacBook is wired up against it).

`docker-01` also hosts BankML's self-hosted MLflow tracking server (`mlflow server` + Postgres +
a Cloudflare Tunnel gated by Cloudflare Access) — see
[mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md](../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md)
and [infrastructure/homelab/mlflow/README.md](../../infrastructure/homelab/mlflow/README.md).
Live and verified reachable at `https://mlflow.homelab-boom.com` (403 without an Access Service
Token, 200 with one), and the deployed Azure Container App authenticates through it correctly on
every request via `src/bankml/tracking_auth.py`'s MLflow request header provider. Artifacts still
live on a local Docker volume, not Azure Blob as ADR-0013 decided.

`monitoring-01` runs Prometheus and Grafana — see
[infrastructure/homelab/monitoring/README.md](../../infrastructure/homelab/monitoring/README.md).
`node_exporter` runs as a systemd service (not a container, since `k8s-01` runs containerd rather
than Docker) on all three VMs; Prometheus scrapes all three and Grafana renders a provisioned
"Homelab Overview" dashboard (CPU, memory, disk, network, up/down) per host. Host-level metrics
only so far — per-container, per-pod and BankML application metrics are still open.

All three on the SSD-backed storage pool for their root disks; bulky, non-latency-sensitive data
(Prometheus's TSDB, container image cache, ISO images) goes on the HDD-backed pool instead. No
VLAN segmentation yet — all three sit on the flat LAN described in
[network-topology.md](../network/network-topology.md).

## Planned hardware

The current desktop is a placeholder. The long-term plan replaces it with a significantly more
capable server/workstation that becomes both the permanent homelab and a secondary engineering
workstation — at which point decisions made under "current hardware is non-redundant and
temporary" (like keeping the DVC remote on Azure) get revisited on their own merits, not
automatically migrated.

## What's not decided yet

Deliberately left open, each to be resolved by its own ADR when that phase is actually reached:

- Where training compute runs for anything heavier than local CPU training
- The specific VPN technology and configuration (see
  [network-topology.md](../network/network-topology.md))

This list should shrink over time as those ADRs get written — if this section is still this long
a few phases from now, that's worth noticing.
