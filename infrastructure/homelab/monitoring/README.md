# Prometheus and Grafana on monitoring-01

Docker Compose stack for the homelab's own monitoring, per
[ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md). Runs on `monitoring-01`
(192.168.1.136).

## Current state

`node_exporter` runs as a systemd service directly on all three VMs (`k8s-01`, `docker-01`,
`monitoring-01`) and on the Proxmox host itself (`pve01`) — a static binary, not a container,
since `k8s-01` runs containerd rather than Docker and a systemd service is the one deployment
method that works identically everywhere, hypervisor included. Prometheus (on `monitoring-01`)
scrapes the three VMs over the LAN and the Proxmox host over its Tailscale address (no other
documented route to it that isn't a LAN IP a DHCP renewal could change under it), and Grafana
visualises all four through the same provisioned "Homelab Overview" dashboard: CPU, memory, disk
and network per host, plus an up/down panel. Every panel is queried by the generic `role` label
each scrape job sets, not hardcoded per host — the Proxmox host required a new scrape target in
`prometheus.yml` and nothing else; the dashboard picked it up automatically.

The Proxmox host is arguably the single most consequential machine to have visibility into —
every VM here runs on top of it — so it not being monitored was a real gap, not a deliberate
simplification, closed once it was noticed rather than left for later.

Prometheus also scrapes BankML's deployed serving app directly over the public internet
(`GET https://bankml-credit-serving.../metrics`, see `mlops/src/bankml/serving/metrics.py`), and
a second provisioned dashboard, "BankML Serving", shows request rate by endpoint and status,
p95 latency, and predictions by decision. That endpoint has no authentication of its own — same
exposure the app's existing `/health` and `/predict/credit` already have — so this is scraping a
genuinely public URL, not something inside the LAN. It will read `down` until the deployed
Container App is rebuilt and redeployed with the `/metrics` route on it; a scale-to-zero cold
start can also make the very first scrape after idle time-out, which is expected, not a bug.

This covers host-level metrics (all three VMs and the Proxmox host) and BankML's serving app. Not
yet covered: per-container metrics on `docker-01` (cAdvisor), or k3s/pod-level metrics on
`k8s-01` (kube-state-metrics).

A Prometheus Pushgateway also runs here (port 9091) — `mlops`'s drift job
(`mlops/src/bankml/monitoring/drift.py`, `make drift DOMAIN=credit`) is a one-shot batch job, not
a server Prometheus can scrape directly, so it pushes its results here instead after each run.
Two Grafana alert rules (`grafana/provisioning/alerting/drift.yaml`) watch what lands: one fires
when drift crosses its configured PSI threshold, the other fires if the job hasn't pushed
anything in over 2 days (silently-stopped-running is otherwise invisible with a Pushgateway,
since it just keeps returning the last value forever). Both verified firing for real against a
real drift run, not just provisioned and assumed to work.

Alerts actually reach somewhere: a Discord contact point, with the default notification policy
routed to it. Grafana's generic webhook contact point sends its own fixed JSON envelope with no
way to reduce it to a plain-text body — confirmed by inspection (pointing a temporary contact
point at a URL that echoed back exactly what Grafana sent), not assumed — so a plain webhook
target like ntfy.sh would just show a raw JSON dump, not a clean message. Discord has native,
well-formatted support built into Grafana, so that's what's wired up; verified with a real test
notification landing in the channel.

The Discord webhook URL is a credential and isn't in this repository — same treatment as every
other secret here. Set up on a fresh deploy:

```bash
GRAFANA_PW=...  # from .env on monitoring-01
curl -s -u admin:$GRAFANA_PW -X POST http://localhost:3000/api/v1/provisioning/contact-points \
  -H 'Content-Type: application/json' \
  -d '{"name":"discord-alerts","type":"discord","settings":{"url":"<your Discord webhook URL>","use_discord_username":true}}'

curl -s -u admin:$GRAFANA_PW -X PUT http://localhost:3000/api/v1/provisioning/policies \
  -H 'Content-Type: application/json' \
  -d '{"receiver":"discord-alerts","group_by":["grafana_folder","alertname"]}'
```

Not file-provisioned deliberately — a committed contact-point file would need either a real
secret in git or a placeholder that could silently overwrite the real one on a restart
(file-provisioned resources reconcile on every Grafana startup). The API-created state persists
in Grafana's own database volume; this is the one-time setup for a genuinely fresh deploy only.

## Deploying

`node_exporter` first, on each of the three VMs **and on the Proxmox host itself**, over SSH:

```bash
curl -sL -o node_exporter.tar.gz \
  https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter.tar.gz
sudo mv node_exporter-1.8.2.linux-amd64/node_exporter /usr/local/bin/node_exporter
sudo useradd --no-create-home --shell /usr/sbin/nologin node_exporter
sudo tee /etc/systemd/system/node_exporter.service >/dev/null <<'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
rm -rf node_exporter.tar.gz node_exporter-1.8.2.linux-amd64
```

On the Proxmox host (`root@100.115.148.123`), drop every `sudo` — Proxmox doesn't provision a
separate sudo user by default, so this runs directly as `root`.

Then the stack itself, on `monitoring-01`:

```bash
git clone https://github.com/martinusboomuc/ai-infrastructure-lab.git
cd ai-infrastructure-lab/infrastructure/homelab/monitoring
cp .env.example .env
# edit .env with a real GRAFANA_ADMIN_PASSWORD

docker compose up -d
```

Check it came up:

```bash
docker compose ps
curl http://localhost:9090/-/healthy
curl http://localhost:3000/api/health
```

## Using it

- Prometheus: `http://192.168.1.136:9090` — Status > Targets should show all five jobs
  (`prometheus`, `node-k8s-01`, `node-docker-01`, `node-monitoring-01`, `bankml-credit-serving`)
  as `UP` — `bankml-credit-serving` only once the deployed Container App has been redeployed with
  the `/metrics` route.
- Grafana: `http://192.168.1.136:3000` — log in as `admin` with `GRAFANA_ADMIN_PASSWORD`. Both the
  Prometheus data source and the two dashboards ("Homelab Overview", "BankML Serving") are
  provisioned automatically, not added by hand — editing either in the UI won't persist across a
  container recreate, since both are owned by files in `grafana/provisioning/`.

## Updating

```bash
cd ai-infrastructure-lab/infrastructure/homelab/monitoring
git pull
docker compose up -d --build
```

A change to `prometheus.yml` or anything under `grafana/provisioning/` needs a restart to be
picked up:

```bash
docker compose restart prometheus grafana
```

## Tearing down

```bash
docker compose down
```

Add `-v` to also delete Prometheus's TSDB and Grafana's own database (dashboards created by hand
in the UI, if any) — not just stop the containers.

## What's still open

- Per-container metrics on `docker-01` (cAdvisor) and k3s/pod-level metrics on `k8s-01`
  (kube-state-metrics).
- BankML's own drift job (`make drift`, `mlops/src/bankml/monitoring/drift.py`) has real,
  verified-firing Grafana alert rules (`grafana/provisioning/alerting/drift.yaml`) that reach a
  real Discord channel — but nothing else in the stack alerts at all. A host or the serving app
  itself going down still pages no one; only drift detection does right now.
- The BankML scrape target is a hardcoded Azure FQDN in `prometheus.yml`, not derived from
  anything — if the Container App is ever recreated with a different auto-generated hostname
  segment, this needs a manual update.
- `node_exporter`'s IP-based scrape targets in `prometheus.yml` are DHCP leases, not static
  reservations, same caveat as `docs/architecture/homelab-architecture.md`'s VM layout table.
