# ADR-0001: Hybrid infrastructure: homelab for self-hosted services, cloud for managed ones

**Status:** Accepted
**Date:** 2026-09-18

## Context

This lab's own stated long-term goal (see the workspace Dashboard) is to gain the technical
depth to design, deploy and maintain production-grade AI infrastructure — which means real
experience with both self-hosted infrastructure and managed cloud services, not a preference for
one over the other. Left undecided, every future project (BankML's later phases, and whatever
comes after it) would have to re-litigate "should this run on the homelab or in the cloud" from
scratch, project by project.

A homelab machine exists and is already partially operational: a repurposed older desktop (Intel
Core i5, 5th generation; 16 GB DDR3 RAM; 512 GB SSD; 1 TB HDD; NVIDIA GTX 1050 Ti) running
Proxmox VE. Installation is complete, networking and internet connectivity work, and the machine
is managed headless — no monitor, keyboard or mouse required once booted. Wake-on-LAN is
configured, so it can be powered on remotely from the MacBook. Today, remote management happens
over the local network; external (off-LAN) access is planned for later via VPN, deliberately
never by exposing management interfaces directly to the internet. This hardware is explicitly
temporary — the long-term plan replaces it with a more capable permanent server/workstation.

Separately, BankML (this lab's first real project) already made an infrastructure placement
decision independently, before this ADR existed: its DVC remote runs on Azure Blob Storage
(Phase 2). That decision is not revisited here — see Consequences.

## Decision

Infrastructure is split three ways, by what each piece is actually good for, not by a blanket
preference for either self-hosting or the cloud:

**The MacBook** is a development client only: VS Code, terminal, Git/GitHub, documentation,
remote administration. It does not run infrastructure services, VMs, or heavy workloads, and
does not hold long-term data — `BANKML_DATA_ROOT` is already environment-variable-driven for
exactly this reason (`mlops/docs/mlops/local-setup.md`'s "Migrating to the homelab" section
exists because this was always the intended direction).

**The homelab** (currently the Proxmox desktop, later its permanent replacement) hosts
self-hosted infrastructure components: Linux VMs, Docker, Kubernetes, Terraform testing, the
Prometheus/Grafana monitoring stack, CI/CD experimentation, and MLOps services specifically
where self-hosting is the more useful thing to learn.

**Public cloud** (Azure now, AWS later) is used whenever managed cloud infrastructure is the
industry-standard solution for a given component. The objective is breadth across both models,
not replacing one with the other.

Where any specific service should live (MLflow tracking server, model registry, training
compute) is deliberately not decided here — each gets its own ADR when that phase is actually
reached, informed by this document's default split and by the constraint in Consequences below.

## Alternatives considered

**Cloud-only, no homelab.** Rejected: skips the self-hosted-infrastructure experience that is
this lab's explicit goal, and is more expensive for always-on experimentation (a Kubernetes
cluster, a monitoring stack) than hardware already sitting idle.

**Self-hosted-only, no cloud.** Rejected: skips the equally explicit goal of gaining real
experience with managed, industry-standard cloud services. Also impractical right now regardless
of goals — the current homelab machine is a single, non-redundant, explicitly temporary desktop,
unsuitable as the sole home for anything that can't be lost.

**Homelab as the default for everything infrastructure-related, decided once and for all here.**
Considered but deferred: too rigid to commit to before any specific service's real constraints
are known. Per-service placement is better decided when that phase arrives (see Decision).

## Consequences

- The MacBook stays lightweight — no local Docker/VM sprawl, no long-term data.
- **CI/CD reachability becomes a real constraint the moment anything CI needs to reach is
  homelab-hosted.** Management access is VPN-only by design, never exposed to the internet —
  GitHub Actions' cloud-hosted runners have no path into that VPN. Any future ADR placing a
  service on the homelab (MLflow, a model registry, etc.) must explicitly resolve this: a
  self-hosted GitHub Actions runner living inside the homelab/VPN, keeping that specific service
  cloud-hosted instead, or a narrowly scoped tunnel for just that one endpoint.
- The current homelab machine's single-disk, no-redundancy, temporary nature means it does not
  yet host anything irreplaceable. BankML's DVC remote stays on Azure Blob Storage rather than
  moving to self-hosted storage until the permanent replacement hardware exists.
- GPU-accelerated workloads are not a near-term need: `mlops/README.md` explicitly excludes deep
  learning on tabular data, and BankML's actual champion/challenger models (a WoE scorecard,
  LightGBM) run entirely on CPU. The GTX 1050 Ti's limited VRAM is a non-issue for this project
  as currently scoped — noted here so a future reader doesn't wonder why it wasn't factored in.
- Every future service-placement decision gets its own ADR rather than being decided ad hoc, but
  starts from this document's default split instead of re-litigating cloud-vs-self-hosted from
  first principles each time.
