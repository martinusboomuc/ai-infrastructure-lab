# AI Infrastructure Lab

A professional homelab focused on AI Infrastructure, MLOps, Cloud, DevOps and Cybersecurity.

## Objectives

- Build production-grade infrastructure
- Learn Linux professionally
- Master Git and GitHub workflows
- Deploy applications with Docker and Kubernetes
- Learn Infrastructure as Code using Terraform
- Work with Azure and AWS
- Build real MLOps pipelines
- Develop a professional engineering portfolio

## Repository Structure

```text
docs/
labs/
infrastructure/
containers/
automation/
monitoring/
mlops/
scripts/
assets/
```

## Infrastructure

This lab runs on hybrid infrastructure — a homelab for self-hosted services, public cloud for
managed ones — see [`docs/decisions/0001-hybrid-infrastructure.md`](docs/decisions/0001-hybrid-infrastructure.md)
for why, [`docs/architecture/homelab-architecture.md`](docs/architecture/homelab-architecture.md)
for the current hardware and role split, and
[`docs/network/network-topology.md`](docs/network/network-topology.md) for what's configured and
what's still open.

## Flagship Project — BankML Platform

[**`mlops/`**](mlops/) contains **BankML Platform**: a production-inspired MLOps platform for
banking machine learning, with its own architecture, roadmap and architecture decision records.

It is the largest project in this lab and is developed as a standalone product — see
[`mlops/README.md`](mlops/README.md).

## Technology Stack

- Linux
- Git
- Docker
- Kubernetes
- Terraform
- Azure
- AWS
- Python
- FastAPI
- MLflow
- Prometheus
- Grafana

## Status

Work in progress.
