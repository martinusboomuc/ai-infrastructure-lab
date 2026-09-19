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

See [ADR-0002](../decisions/0002-proxmox-vm-layout.md) for the reasoning. Decided, not yet
provisioned:

| VM | Role | RAM | vCPU | Disk |
| --- | --- | --- | --- | --- |
| `k8s-01` | Single-node k3s (control-plane + worker combined) | 4 GB | 2 | 60 GB |
| `docker-01` | Plain Docker/Compose host for anything outside the cluster | 4 GB | 2 | 40 GB |
| `monitoring-01` | Prometheus + Grafana | 2 GB | 1 | 20 GB |

`docker-01` also hosts BankML's self-hosted MLflow tracking server (`mlflow server` + Postgres +
a Cloudflare Tunnel for scoped reachability from the deployed Azure Container App), artifacts on
Azure Blob rather than local disk — see
[mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md](../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md).
Decided, not yet built; its RAM footprint on `docker-01`'s 4 GB budget still needs checking once
it exists alongside whatever else lands there.

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
