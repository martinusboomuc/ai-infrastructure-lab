# Prometheus and Grafana on monitoring-01

Docker Compose stack for the homelab's own monitoring, per
[ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md). Runs on `monitoring-01`
(192.168.1.136).

## Current state

`node_exporter` runs as a systemd service directly on all three VMs (`k8s-01`, `docker-01`,
`monitoring-01`) — a static binary, not a container, since `k8s-01` runs containerd rather than
Docker and a systemd service is the one deployment method that works identically on all three.
Prometheus (on `monitoring-01`) scrapes all three over the LAN and Grafana visualises them
through a single provisioned "Homelab Overview" dashboard: CPU, memory, disk and network per
host, plus an up/down panel.

This covers host-level metrics only. Not yet covered: per-container metrics on `docker-01`
(cAdvisor), k3s/pod-level metrics on `k8s-01` (kube-state-metrics), or BankML's serving app's own
request latency/throughput/error-rate metrics (the FastAPI app doesn't expose a `/metrics`
endpoint yet) — all separate, later work.

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

- Prometheus: `http://192.168.1.136:9090` — Status > Targets should show all four jobs
  (`prometheus`, `node-k8s-01`, `node-docker-01`, `node-monitoring-01`) as `UP`.
- Grafana: `http://192.168.1.136:3000` — log in as `admin` with `GRAFANA_ADMIN_PASSWORD`. The
  Prometheus data source and the "Homelab Overview" dashboard are provisioned automatically, not
  added by hand — editing either in the UI won't persist across a container recreate, since both
  are owned by files in `grafana/provisioning/`.

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
- BankML's serving app exposing its own `/metrics` (request latency, throughput, error rate) —
  see `mlops/ROADMAP.md` Phase 5.
- Alerting (Alertmanager, or Grafana's own alerting) — nothing pages anyone yet, this is
  dashboards only.
- `node_exporter`'s IP-based scrape targets in `prometheus.yml` are DHCP leases, not static
  reservations, same caveat as `docs/architecture/homelab-architecture.md`'s VM layout table.
