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
- The Proxmox host and the three VMs (`k8s-01`, `docker-01`, `monitoring-01`) are **not** on the
  tailnet themselves — still LAN-only. This isn't a gap in practice: the MacBook is reachable
  from anywhere via Tailscale *and* still sits on the home LAN whenever it's physically there, so
  it acts as the bridge — SSH to the Mac over Tailscale, then SSH from the Mac's own shell to any
  VM exactly as before. Putting the VMs on the tailnet directly is possible later if reaching
  them without the Mac in the loop ever becomes necessary; not needed for anything today.

## Constraint this creates

Per [ADR-0001](../decisions/0001-hybrid-infrastructure.md)'s Consequences: because management
access is VPN-only by design, GitHub Actions' cloud-hosted runners have no path to anything
placed behind that VPN. Any future service placed on the homelab that CI needs to reach (a
metrics endpoint, a registry API, etc.) has to resolve this explicitly — a self-hosted Actions
runner inside the homelab/VPN, keeping that specific service cloud-hosted instead, or a narrowly
scoped tunnel for just that one endpoint. This is a real design constraint on every future
service-placement ADR, not just a networking detail.

## What's not decided yet

- Whether the Proxmox host and its VMs ever join the tailnet directly, instead of being reached
  through the MacBook
- IP addressing / subnet plan for the LAN side
- Firewall rules beyond "nothing exposed directly to the internet"
- Whether/how multiple VMs on the Proxmox host get their own network segmentation
