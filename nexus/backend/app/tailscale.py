"""Live tailnet presence via the `tailscale` CLI, not the Tailscale HTTP API — the CLI reads
straight from `tailscaled`'s local Unix socket (no API key, no network round-trip to Tailscale's
control plane), which is exactly what a backend running on the same host `tailscaled` already
runs on should do. Requires the container this runs in to have `/var/run/tailscale/tailscaled.sock`
bind-mounted from the host and the `tailscale` binary installed in the image — see Dockerfile.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass


@dataclass
class TailscalePeer:
    hostname: str
    os: str
    online: bool
    tailscale_ip: str | None


async def get_tailnet_status() -> list[TailscalePeer]:
    """Every peer on the tailnet, including this host's own `Self` entry — the caller decides
    what to do with each one (map a known hostname to a homelab node, or ignore an unknown peer).
    """
    proc = await asyncio.create_subprocess_exec(
        "tailscale",
        "status",
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"tailscale status failed: {stderr.decode().strip()}")

    data = json.loads(stdout)
    peers = []
    for entry in [data["Self"], *data.get("Peer", {}).values()]:
        ips = entry.get("TailscaleIPs") or []
        # TailscaleIPs lists both an IPv4 and an IPv6 (fd7a:...) address per peer — the IPv4 one
        # is what every other place in this repo already uses (prometheus.yml, SSH commands).
        ipv4 = next((ip for ip in ips if "." in ip), None)
        peers.append(
            TailscalePeer(
                hostname=entry.get("HostName", ""),
                os=entry.get("OS", ""),
                online=bool(entry.get("Online", False)),
                tailscale_ip=ipv4,
            )
        )
    return peers
