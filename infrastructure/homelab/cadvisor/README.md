# cAdvisor on docker-01

Per-container CPU/memory metrics for everything running on `docker-01` (MLflow, Prometheus's
own stack isn't here — that's `monitoring-01` — but any future Compose stack on this host gets
covered automatically). Closes the gap `infrastructure/homelab/monitoring/README.md` names:
`node_exporter` sees the host's aggregate CPU/memory, not which container is responsible for it.

## Deploying

On `docker-01`, over SSH:

```bash
cd ai-infrastructure-lab/infrastructure/homelab/cadvisor
docker compose up -d
```

Check it came up and is actually reporting containers:

```bash
docker compose ps
curl -s http://localhost:8080/metrics | grep container_cpu_usage_seconds_total | head -3
```

`monitoring-01`'s Prometheus scrapes this over the LAN (`192.168.1.115:8080`, job `cadvisor` in
`infrastructure/homelab/monitoring/prometheus.yml`) — no config on this host beyond bringing the
container up; nothing here needs a restart when the scrape side changes.

## Why `privileged: true` and all those read-only host mounts

cAdvisor reads container resource usage directly from the host's cgroup/container filesystem
hierarchy rather than going through the Docker API — the mounts (`/rootfs`, `/sys`,
`/var/lib/docker`, `/dev/disk`) are what let it see that. This is standard for cAdvisor,
documented by the project itself, not something specific to this deployment.

## Tearing down

```bash
docker compose down
```

No volumes — cAdvisor holds no state of its own beyond what it reads live from the host.
