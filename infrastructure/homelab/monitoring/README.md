# Prometheus and Grafana on monitoring-01

Docker Compose stack for the homelab's own monitoring, per
[ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md). Runs on `monitoring-01`
(192.168.1.136).

## Current state

`node_exporter` runs as a systemd service directly on all three VMs (`k8s-01`, `docker-01`,
`monitoring-01`) — a static binary, not a container, since `k8s-01` runs containerd rather than
Docker and a systemd service is the one deployment method that works identically on all three.
Prometheus (on `monitoring-01`) scrapes all three over the LAN and Grafana visualises them
through a provisioned "Homelab Overview" dashboard: CPU, memory, disk and network per host, plus
an up/down panel.

Prometheus also scrapes BankML's deployed serving app directly over the public internet
(`GET https://bankml-credit-serving.../metrics`, see `mlops/src/bankml/serving/metrics.py`), and
a second provisioned dashboard, "BankML Serving", shows request rate by endpoint and status,
p95 latency, and predictions by decision. That endpoint has no authentication of its own — same
exposure the app's existing `/health` and `/predict/credit` already have — so this is scraping a
genuinely public URL, not something inside the LAN. It will read `down` until the deployed
Container App is rebuilt and redeployed with the `/metrics` route on it; a scale-to-zero cold
start can also make the very first scrape after idle time-out, which is expected, not a bug.

This covers host-level metrics and BankML's serving app. Not yet covered: per-container metrics
on `docker-01` (cAdvisor), or k3s/pod-level metrics on `k8s-01` (kube-state-metrics).

## Deploying

`node_exporter` first, on each of the three VMs, over SSH:

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
- Alerting (Alertmanager, or Grafana's own alerting) — nothing pages anyone yet, this is
  dashboards only.
- The BankML scrape target is a hardcoded Azure FQDN in `prometheus.yml`, not derived from
  anything — if the Container App is ever recreated with a different auto-generated hostname
  segment, this needs a manual update.
- `node_exporter`'s IP-based scrape targets in `prometheus.yml` are DHCP leases, not static
  reservations, same caveat as `docs/architecture/homelab-architecture.md`'s VM layout table.
