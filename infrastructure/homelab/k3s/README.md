# kube-state-metrics on k8s-01

Pod/deployment/daemonset-level cluster state for Prometheus. Closes the gap
`infrastructure/homelab/monitoring/README.md` names: `node_exporter` sees `k8s-01`'s own
CPU/memory as a single Linux host, not what's actually running inside the k3s cluster on top of
it — this is what does.

`kube-state-metrics.yaml` is the upstream v2.13.0 manifest (ServiceAccount, ClusterRole,
ClusterRoleBinding, Deployment, Service), pinned and applied directly rather than through Helm —
matches `node_exporter`'s own explicit-versioned-artifact convention elsewhere in this repo. The
one change from upstream: the Service is `NodePort` (fixed at `30080`), not the original headless
`ClusterIP` — `monitoring-01` runs Prometheus outside the k3s cluster entirely, on a separate VM,
and a ClusterIP address has no meaning from there. See the file's own header comment for the
full reasoning.

## Deploying

On `k8s-01`, over SSH:

```bash
cd ai-infrastructure-lab/infrastructure/homelab/k3s
sudo k3s kubectl apply -f kube-state-metrics.yaml
```

Check it came up:

```bash
sudo k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=kube-state-metrics
sudo k3s kubectl -n kube-system get svc kube-state-metrics
curl -s http://localhost:30080/metrics | grep kube_pod_status_phase | head -3
```

`monitoring-01`'s Prometheus scrapes this over the LAN (`192.168.1.183:30080`, job
`kube-state-metrics` in `infrastructure/homelab/monitoring/prometheus.yml`) — no config on this
host beyond applying the manifest; nothing here needs touching when the scrape side changes.

## Cluster DNS

CoreDNS forwards names outside the cluster to the resolvers in the file the kubelet is given.
By default that is the node's own list, which on `k8s-01` starts with Tailscale's
`100.100.100.100`. That resolver does not answer queries forwarded from pods, so public lookups
from pods failed or came back with IPv6 addresses only, depending on which upstream CoreDNS
picked. Pods have no IPv6 route, so those lookups failed too.

`node/` holds the fix, installed on `k8s-01` as `/etc/rancher/k3s/config.yaml` and
`/etc/rancher/k3s/resolv.conf`. It gives k3s a resolver file that lists only the router:

```bash
sudo install -m 0644 node/config.yaml /etc/rancher/k3s/config.yaml
sudo install -m 0644 node/resolv.conf /etc/rancher/k3s/resolv.conf
sudo systemctl restart k3s
sudo k3s kubectl -n kube-system rollout restart deploy/coredns
```

Pods cannot resolve tailnet names (`*.ts.net`) as a result. Nothing in the cluster needs them:
Nexus reads presence through the Tailscale API and reaches the other VMs by LAN address.

## Tearing down

```bash
sudo k3s kubectl delete -f kube-state-metrics.yaml
```

No persistent state — kube-state-metrics only ever reflects the cluster's current state, read
live from the Kubernetes API.
