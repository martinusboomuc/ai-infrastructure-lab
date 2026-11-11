# AI Infrastructure Lab

Hybrid infrastructure for machine learning in production: a self-hosted Proxmox homelab for the
services worth running myself, and Azure for the managed ones. Everything here is deployed and
running, not mocked. Each design decision is recorded as an architecture decision record (ADR),
and known limitations are written down rather than left out.

The lab contains three projects. Each one is documented on its own and can be read on its own.

| Project | What it is | What it demonstrates |
| --- | --- | --- |
| [BankML Platform](mlops/) | MLOps platform for banking ML, live on Azure | The full model lifecycle, from point-in-time-correct features to drift-triggered retraining, built so that a second domain plugs in without rewriting the core |
| [Homelab](infrastructure/homelab/) | Proxmox host with three VMs, provisioned by Terraform | Infrastructure as code, Kubernetes, observability, and private networking on real hardware |
| [Nexus](nexus/) | Live command center for the homelab | A full-stack application (FastAPI, React) that reads the same live sources as the monitoring stack |

## Architecture

```text
                      Tailscale mesh (WireGuard, nothing exposed publicly)
   MacBook ────────────────────────┬───────────────────────────────── iPhone
                                   │
   ┌───────────────────────────────┴─────────────────────────────────────────┐
   │ pve01: Proxmox VE (Terraform, cloud-init)                               │
   │                                                                         │
   │  k8s-01             docker-01                     monitoring-01         │
   │  k3s                MLflow + Postgres             Prometheus            │
   │  kube-state-        BankML training               Grafana               │
   │  metrics            Nexus                         Pushgateway           │
   │                     cAdvisor                                            │
   │                                                                         │
   │  node_exporter on every host  →  Prometheus  →  Grafana  →  Discord     │
   └────────────────────────────┬────────────────────────────────────────────┘
                                │ Cloudflare Tunnel + Access (MLflow only)
   ┌────────────────────────────┴────────────────────────────────────────────┐
   │ Azure                                                                   │
   │  Container Apps: BankML serving API (image from GHCR)                   │
   │  Blob Storage: DVC data remote, MLflow artifacts, prediction log        │
   └─────────────────────────────────────────────────────────────────────────┘

   GitHub Actions: lint and test BankML pull requests · build, push and deploy
```

The split between self-hosted and managed services is decided in
[ADR-0001](docs/decisions/0001-hybrid-infrastructure.md). The hardware and VM layout are in
[homelab-architecture.md](docs/architecture/homelab-architecture.md), and the network, including
what is still undecided, is in [network-topology.md](docs/network/network-topology.md).

## BankML Platform

A Credit Risk model, a WoE scorecard champion with a LightGBM challenger, is served from Azure
Container Apps. Every decision it returns carries SHAP-derived reason codes. The platform covers:

- Point-in-time-correct feature construction, enforced by a leakage test
- Pandera data contracts at every pipeline boundary
- Experiment tracking and a model registry in a self-hosted MLflow
- An evaluation gate that decides promotion on its own merits
- Drift detection with Evidently, alerting through Prometheus, Grafana and Discord
- Retraining triggered by drift, which the gate can still refuse to promote

Fraud Detection was added afterwards as the portability test. All fraud-specific logic lives in
one config file, one feature module and one validation schema. The one change it forced in the
core, a third model type, is documented in [ROADMAP.md](mlops/ROADMAP.md) rather than hidden.
Fourteen ADRs record the reasoning: [mlops/docs/decisions](mlops/docs/decisions/).

## Homelab

A repurposed desktop runs Proxmox VE: Intel Core i5 (5th generation), 16 GB RAM, an SSD pool for
VM root disks and an HDD pool for bulk data. Terraform
([`bpg/proxmox`](https://registry.terraform.io/providers/bpg/proxmox/latest/docs)) and cloud-init
provision the three VMs. Prometheus scrapes every host and the hypervisor itself. Alert rules
cover unreachable targets, sustained CPU and memory pressure, full disks and failed pods, and
route to Discord.

Problems solved on this hardware, each documented with the exact error and the cause:

- A KVM-only guest kernel panic, isolated to the CPU's ACPI C-states and fixed with a kernel boot
  parameter applied to both GRUB configurations of a UEFI install
- A cloud-init override that silently dropped hostname and user provisioning
- Wake-on-LAN failing from macOS because of limited versus directed broadcast

## Nexus

A FastAPI backend combines live Tailscale presence with Prometheus health, using the same PromQL
as the Grafana dashboards so the two views never disagree. A React Flow frontend renders the
result as a live topology graph. Clicking a node shows its status and links straight to the tool
behind it: Grafana, Prometheus, MLflow or the Proxmox web UI. It runs on `docker-01` behind nginx.
The roadmap ends with a local LLM copilot on the host's unused GPU: [nexus/README.md](nexus/).

## How the work is done

- **Decisions:** 16 ADRs across the lab and BankML, each written before or alongside the change
  it justifies.
- **CI/CD:** GitHub Actions lints and tests every pull request that touches BankML (30 pytest
  modules), and builds, pushes and deploys the serving image.
- **Commits:** small, one logical change each, with plain imperative messages.
- **Learning log:** every working session is recorded with the problems hit, the exact error
  messages, and why each fix worked. A one-way sync (`scripts/sync_notion.py`) publishes project
  state from this repository to that log, never the reverse.

## Known limitations

- The homelab is a single consumer machine with no RAID and no off-host backup. Nothing
  irreplaceable lives only on it, which is why BankML's data remote stays on Azure.
- The KVM boot-parameter fix reduces the guest panic rate rather than eliminating it. An
  occasional VM still needs one restart after a fresh host boot.
- The LAN has no static addressing plan, no firewall rules beyond "nothing exposed publicly", and
  no VLAN segmentation. All three are recorded as open in network-topology.md.
- BankML's data is a static public dataset (Home Credit, and Sparkov for fraud), so there is no
  live ingestion. Drift is tested by injecting it.
