"""Active Grafana alerts, the same ones the Discord channels receive, read from Grafana's built-in
Alertmanager API with a service account token that holds only the Viewer role.

The token is optional. Without one, the endpoint reports that alerts are not configured instead
of failing, so Nexus still runs before the token exists.

The Discord links are channel URLs (discord.com/channels/<server>/<channel>), which only open the
channel for someone already in the server. They are not the webhook URLs Grafana posts to: those
are credentials and stay out of Nexus entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from app.links import GRAFANA_URL, QuickLink

# Reached from inside the cluster, which may differ from the URL a browser should open.
GRAFANA_API_URL = os.environ.get("GRAFANA_API_URL", GRAFANA_URL)


@dataclass
class Alert:
    name: str
    folder: str
    severity: str
    target: str
    summary: str
    starts_at: str
    silenced: bool


@dataclass
class AlertsResponse:
    configured: bool
    alerts: list[Alert]
    channels: list[QuickLink]
    grafana_url: str
    error: str | None = None


def discord_channels() -> list[QuickLink]:
    channels = [
        ("#homelab-alerts", os.environ.get("DISCORD_HOMELAB_CHANNEL_URL")),
        ("#bankml-alerts", os.environ.get("DISCORD_BANKML_CHANNEL_URL")),
    ]
    return [QuickLink(label, url) for label, url in channels if url]


def _target(labels: dict[str, str]) -> str:
    # The homelab rules are multi-dimensional, so the affected host or pod is a label, not part
    # of the rule's name.
    if "pod" in labels:
        return f"{labels.get('namespace', '')}/{labels['pod']}".lstrip("/")
    return labels.get("role") or labels.get("job") or ""


async def get_alerts() -> AlertsResponse:
    channels = discord_channels()
    browser_url = f"{GRAFANA_URL}/alerting/list"
    token = os.environ.get("GRAFANA_TOKEN")
    if not token:
        return AlertsResponse(False, [], channels, browser_url)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{GRAFANA_API_URL}/api/alertmanager/grafana/api/v2/alerts",
                params={"active": "true", "silenced": "true", "inhibited": "false"},
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        raw = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return AlertsResponse(True, [], channels, browser_url, error=type(exc).__name__)

    alerts = [
        Alert(
            name=item["labels"].get("alertname", ""),
            folder=item["labels"].get("grafana_folder", ""),
            severity=item["labels"].get("severity", ""),
            target=_target(item["labels"]),
            summary=item.get("annotations", {}).get("summary", ""),
            starts_at=item.get("startsAt", ""),
            silenced=item.get("status", {}).get("state") == "suppressed",
        )
        for item in raw
    ]
    alerts.sort(key=lambda a: a.starts_at, reverse=True)
    return AlertsResponse(True, alerts, channels, browser_url)
