# ADR-0002: Proxmox VM layout — three VMs split by role

**Status:** Accepted
**Date:** 2026-09-20

## Context

[ADR-0001](0001-hybrid-infrastructure.md) put Linux VMs, Docker, Kubernetes, Terraform testing,
the Prometheus/Grafana monitoring stack, and CI/CD experimentation on the homelab, and explicitly
left the exact VM layout for a later ADR once needed
(`docs/architecture/homelab-architecture.md`, "What's not decided yet").

The current hardware is a fixed, known constraint: 16 GB DDR3 RAM, one non-redundant machine,
explicitly temporary. RAM is the binding resource — CPU core/thread count for this specific 5th
generation i5 has not been confirmed with `lscpu` on the host, so vCPU counts below are a
starting allocation to revisit once that's known, not a hard budget the way RAM is.

A full multi-node Kubernetes cluster built the production way (kubeadm, separate control-plane
and worker nodes) needs several VMs at 2 GB+ each just for the control plane, which does not fit
this machine alongside anything else. Something has to give: either the number of VMs, or how
production-realistic the Kubernetes setup is.

## Decision

Three VMs, split by role, on a flat network (no VLAN segmentation — that stays
`network-topology.md`'s open item, not this one):

| VM | Role | RAM | vCPU | Disk | Storage backend |
|---|---|---|---|---|---|
| `k8s-01` | Single-node k3s (control-plane + worker combined) | 4 GB | 2 | 60 GB | SSD |
| `docker-01` | Plain Docker/Compose host for anything outside the cluster | 4 GB | 2 | 40 GB | SSD |
| `monitoring-01` | Prometheus + Grafana | 2 GB | 1 | 20 GB | SSD (Prometheus TSDB data on HDD) |

10 GB RAM / 5 vCPU assigned, leaving roughly 4 GB (after Proxmox's own overhead) unallocated
rather than dividing the box to its last megabyte — headroom for ballooning, snapshots, and
running things concurrently without swapping.

VM root disks live on the SSD-backed storage pool; anything bulky and not latency-sensitive
(Prometheus's time-series data, container image cache, ISO images) goes on the HDD-backed pool
instead.

No self-hosted CI runner VM is provisioned by this ADR. Per ADR-0001's Consequences, one is only
needed once a specific homelab-hosted service actually requires GitHub Actions to reach it — an
idle runner VM would just consume RAM that the three VMs above already spend to zero slack.

GPU passthrough for the GTX 1050 Ti is out of scope here too, for the same reason ADR-0001 gave:
no current workload needs it.

## Alternatives considered

**Multi-node kubeadm cluster (control-plane + 2 workers).** Rejected: needs 3-4 VMs at 2 GB+
each before running a single workload, which leaves nothing for Docker or monitoring on 16 GB
total. More production-realistic, but not viable on this hardware — revisit on the planned
replacement hardware (`homelab-architecture.md`, "Planned hardware").

**One VM for everything.** Rejected: defeats the purpose of practicing the role split this lab
is meant to teach, and puts the monitoring stack on the same failure domain as what it monitors
— it can't report that a VM is down from inside that VM.

**Four-plus VMs (separate CI runner and/or separate ingress/registry VM now).** Rejected:
nothing today needs a CI runner reachable over the VPN, and a registry can run as a container on
`docker-01` until it earns its own VM. Adding VMs ahead of an actual need is exactly the kind of
premature segmentation this hardware can't afford.

## Consequences

- `k8s-01` running k3s instead of a multi-node kubeadm cluster means single-node failure modes
  (etcd, control-plane) aren't exercised here — that gap is accepted until the permanent
  replacement hardware exists.
- Adding a fourth VM later (a CI runner, a registry, a second Kubernetes node) means either
  reducing an existing VM's RAM or waiting for the replacement hardware; there is no free
  headroom for a same-sized fourth VM today.
- Terraform work targeting the homelab provisions against this three-VM shape; a Terraform
  change that assumes a multi-node cluster or a fourth always-on VM contradicts this ADR and
  should update it first, not route around it.
- Prometheus's data directory living on the HDD backend means its query latency is bounded by
  spinning-disk I/O, not SSD — acceptable for a homelab-scale metrics volume, called out here so
  it isn't mistaken for an oversight later.
