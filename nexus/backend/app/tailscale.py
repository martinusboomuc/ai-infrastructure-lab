"""Live tailnet presence via the Tailscale HTTP API, authenticated with an OAuth client that holds
only the `devices:core:read` scope. The backend runs as a pod on k3s, so it cannot assume the
node it lands on has `tailscaled` or that its socket is safe to mount: the socket grants the full
LocalAPI, far more than reading a device list needs. See docs/decisions/0003.

The client ID and secret come from the environment (a Kubernetes Secret in production). Access
tokens are valid for one hour and are reused until shortly before they expire.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

API_URL = "https://api.tailscale.com/api/v2"
# `-` is the API's alias for the tailnet the OAuth client belongs to.
TAILNET = os.environ.get("TS_TAILNET", "-")
# Refresh this long before the token's stated expiry, so a request never races it.
_EXPIRY_MARGIN_S = 60


@dataclass
class TailscalePeer:
    hostname: str
    os: str
    online: bool
    tailscale_ip: str | None


@dataclass
class _Token:
    value: str
    expires_at: float


_token: _Token | None = None


async def _access_token(client: httpx.AsyncClient) -> str:
    global _token
    if _token and time.monotonic() < _token.expires_at:
        return _token.value

    response = await client.post(
        f"{API_URL}/oauth/token",
        data={
            "client_id": os.environ["TS_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["TS_OAUTH_CLIENT_SECRET"],
        },
        timeout=5.0,
    )
    response.raise_for_status()
    body = response.json()
    _token = _Token(
        value=body["access_token"],
        expires_at=time.monotonic() + body["expires_in"] - _EXPIRY_MARGIN_S,
    )
    return _token.value


async def get_tailnet_status() -> list[TailscalePeer]:
    """Every device on the tailnet. The caller decides what to do with each one (map a known
    hostname to a homelab node, or ignore an unknown device).
    """
    async with httpx.AsyncClient() as client:
        token = await _access_token(client)
        response = await client.get(
            f"{API_URL}/tailnet/{TAILNET}/devices",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
    response.raise_for_status()

    peers = []
    for device in response.json()["devices"]:
        # `addresses` lists both an IPv4 and an IPv6 (fd7a:...) address per device. The IPv4 one
        # is what every other place in this repo already uses (prometheus.yml, SSH commands).
        ipv4 = next((ip for ip in device.get("addresses", []) if "." in ip), None)
        peers.append(
            TailscalePeer(
                hostname=device.get("hostname", ""),
                os=device.get("os", ""),
                # True while the device holds a connection to the coordination server, the same
                # signal `tailscale status` reports as online.
                online=bool(device.get("connectedToControl", False)),
                tailscale_ip=ipv4,
            )
        )
    return peers
