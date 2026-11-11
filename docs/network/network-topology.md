# Network topology

Companion to [homelab-architecture.md](../architecture/homelab-architecture.md) and
[ADR-0001](../decisions/0001-hybrid-infrastructure.md). This document is intentionally sparse —
it records what's actually configured today and what's decided about the plan, not a guessed-at
full topology. Sections marked TBD are genuinely undecided, not omitted by accident.

## Today

- MacBook and the homelab Proxmox host are on the same local network.
- **Wake-on-LAN** is configured and working from the MacBook to the Proxmox host (`pve01`,
  `192.168.1.10`). The magic-packet target is `f4:4d:30:13:f3:ff` — this is the physical NIC's
  (`nic0`) address; `vmbr0` reports the identical MAC only because `nic0` is its sole bridge
  member, not because the two happen to coincide. WoL is armed persistently via
  `/etc/network/interfaces`'s `nic0` stanza (`post-up /usr/sbin/ethtool -s nic0 wol g`), so it
  survives a reboot with no separate systemd unit needed. Confirmed for real: a clean
  `shutdown -h now` on the host left the NIC's link/activity lights lit (standby power to the
  card is intact — BIOS/ErP is not cutting it), and the host woke from the MacBook afterward.

  The actual fault was on the macOS side, not the server. Plain `wakeonlan f4:4d:30:13:f3:ff`
  (limited broadcast, `255.255.255.255`) sends without error but never reaches the host; `wakeonlan
  -i 192.168.1.255 f4:4d:30:13:f3:ff` (the LAN's directed broadcast address) does. macOS does not
  reliably deliver `255.255.255.255` as an L2 broadcast on this network the way a subnet-directed
  broadcast does — any WoL invocation from this MacBook needs `-i 192.168.1.255`, not the limited
  broadcast address.
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
- **DNS on the VMs goes through `systemd-resolved`**, with Tailscale configuring it over DBus:
  tailnet names go to `100.100.100.100`, everything else to the router (`192.168.1.1`).
  `/etc/resolv.conf` must stay a symlink to `/run/systemd/resolve/stub-resolv.conf`.

  On `k8s-01` and `monitoring-01` it was not. Tailscale had overwritten `/etc/resolv.conf` with
  a plain file listing only `100.100.100.100`, with no upstream to forward public names to.
  `tailscaled` logged `dns: resolver: forward: no upstream resolvers set, returning SERVFAIL`,
  and every public lookup failed. k3s could not pull images (`lookup registry-1.docker.io: Try
  again`), and Grafana could not resolve `discord.com`, so Discord alerts had no route out even
  though nothing reported an error. `docker-01` had the same fault after the September power
  outage, when it broke the Cloudflare Tunnel, and was fixed then. The other two VMs were not
  checked at the time, and stayed broken for two months.

  The fix on each VM restores the symlink and restarts `tailscaled`, which then detects
  `systemd-resolved` and uses it:

  ```bash
  sudo ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
  sudo systemctl restart tailscaled
  ```

  Two follow-ups were needed. Docker copies the resolver config when a container starts, so
  Grafana needed a restart. k3s chooses the kubelet's `resolvConf` at startup and had pinned the
  old file. With a loopback stub in its place, `systemctl restart k3s` switches it to
  `/run/systemd/resolve/resolv.conf`, then `kubectl -n kube-system rollout restart
  deploy/coredns` makes CoreDNS use it. Tailscale is installed by hand, not by cloud-init, so a
  rebuilt VM needs this checked again.

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
