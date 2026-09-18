# Network topology

Companion to [homelab-architecture.md](../architecture/homelab-architecture.md) and
[ADR-0001](../decisions/0001-hybrid-infrastructure.md). This document is intentionally sparse —
it records what's actually configured today and what's decided about the plan, not a guessed-at
full topology. Sections marked TBD are genuinely undecided, not omitted by accident.

## Today

- MacBook and the homelab Proxmox host are on the same local network.
- Wake-on-LAN is configured and working from the MacBook to the homelab host.
- Remote management of the homelab (Proxmox web UI, SSH) happens over the local network only.
  Nothing on the homelab is exposed to the public internet today.

## Planned

- **External (off-LAN) access via VPN**, so the homelab can be managed and reached from outside
  the local network without exposing management interfaces directly to the internet.
- Specific VPN technology (e.g. WireGuard, Tailscale, OpenVPN), addressing/subnet layout, and
  firewall rules: **TBD** — to be decided and documented here once chosen, not before.

## Constraint this creates

Per [ADR-0001](../decisions/0001-hybrid-infrastructure.md)'s Consequences: because management
access is VPN-only by design, GitHub Actions' cloud-hosted runners have no path to anything
placed behind that VPN. Any future service placed on the homelab that CI needs to reach (a
metrics endpoint, a registry API, etc.) has to resolve this explicitly — a self-hosted Actions
runner inside the homelab/VPN, keeping that specific service cloud-hosted instead, or a narrowly
scoped tunnel for just that one endpoint. This is a real design constraint on every future
service-placement ADR, not just a networking detail.

## What's not decided yet

- VPN technology and configuration
- IP addressing / subnet plan
- Firewall rules beyond "nothing exposed directly to the internet"
- Whether/how multiple VMs on the Proxmox host get their own network segmentation
