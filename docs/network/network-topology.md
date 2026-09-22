# Network topology

Companion to [homelab-architecture.md](../architecture/homelab-architecture.md) and
[ADR-0001](../decisions/0001-hybrid-infrastructure.md). This document is intentionally sparse —
it records what's actually configured today and what's decided about the plan, not a guessed-at
full topology. Sections marked TBD are genuinely undecided, not omitted by accident.

## Today

- MacBook and the homelab Proxmox host are on the same local network.
- Wake-on-LAN is configured and working from the MacBook to the homelab host.
- **External (off-LAN) access is Tailscale**, decided and set up: the MacBook and the repository
  owner's iPhone are both on the same tailnet (WireGuard-based mesh, no port forwarding, nothing
  exposed to the public internet — matches the "management interfaces never exposed directly"
  principle exactly). SSH to the MacBook now works from anywhere via its Tailscale address, not
  only from the home LAN.
- The three VMs (`k8s-01`, `docker-01`, `monitoring-01`) are **also** on the tailnet directly —
  joined via a reusable Tailscale auth key (`tailscale up --authkey=... --ssh`), not a one-off
  manual login each, so re-joining or adding a future VM is one command, not a browser flow per
  machine. Reachable from anywhere by their own Tailscale addresses, independent of whether the
  MacBook is on or reachable at all — confirmed for real: SSH from the Mac to each VM's Tailscale
  IP succeeded on first connection. `--ssh` also enables Tailscale's own SSH server on each VM
  (identity-based access via the tailnet, alongside the existing key-based OpenSSH access — not a
  replacement for it).
- The Proxmox **host** itself (`pve01`) is also on the tailnet, the same way as the VMs — its
  own web UI (`https://<tailscale-ip>:8006`) and SSH both confirmed reachable directly, with
  `tailscaled` enabled to survive a reboot. Every machine in the homelab is now independently
  reachable from anywhere; none of them depends on another (including the MacBook) being on or
  reachable to bridge to it.

## Constraint this creates

Per [ADR-0001](../decisions/0001-hybrid-infrastructure.md)'s Consequences: because management
access is VPN-only by design, GitHub Actions' cloud-hosted runners have no path to anything
placed behind that VPN. Any future service placed on the homelab that CI needs to reach (a
metrics endpoint, a registry API, etc.) has to resolve this explicitly — a self-hosted Actions
runner inside the homelab/VPN, keeping that specific service cloud-hosted instead, or a narrowly
scoped tunnel for just that one endpoint. This is a real design constraint on every future
service-placement ADR, not just a networking detail.

## What's not decided yet

- IP addressing / subnet plan for the LAN side
- Firewall rules beyond "nothing exposed directly to the internet"
- Whether/how multiple VMs on the Proxmox host get their own network segmentation
