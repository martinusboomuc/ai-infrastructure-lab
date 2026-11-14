# ADR-0003: Run Nexus on k3s, reading tailnet presence through the Tailscale API

**Status:** Accepted
**Date:** 2026-11-11

## Context

[ADR-0002](0002-proxmox-vm-layout.md) gave `k8s-01` a single-node k3s cluster, but until now
the only workload on it was `kube-state-metrics`, which only reports on the cluster itself. Every
application in the lab ran on `docker-01` under Docker Compose.

Nexus is the natural first workload to move. It holds no state, has two services, and is already
built as container images. Two parts of its Compose deployment do not carry over to a cluster:

- The backend read tailnet presence by running `tailscale status --json` against the host's
  `tailscaled` socket, bind-mounted into the container. In Kubernetes that becomes a `hostPath`
  volume. It ties the pod to a node that runs `tailscaled`, and the socket exposes the full
  LocalAPI, which can change the node's Tailscale configuration. Nexus only needs to read a list
  of devices.
- The images were built on `docker-01` by `docker compose up --build`. A cluster pulls images
  from a registry, and nothing recorded which source version was running.

## Decision

Nexus runs on k3s from the Kustomize manifests in `nexus/deploy/k8s/`, in its own `nexus`
namespace, and is reached through the Traefik ingress that ships with k3s.

The backend reads presence from the Tailscale HTTP API (`GET /tailnet/-/devices`). It
authenticates with an OAuth client that holds only the `devices:core:read` scope. The client ID
and secret live in a Kubernetes Secret created by hand and never committed. The API's
`connectedToControl` field replaces the CLI's `Online` flag.

A GitHub Actions workflow (`.github/workflows/nexus-images.yml`) lints both services, builds
their images and pushes them to GHCR, tagged with the commit SHA. The manifests pin those tags,
so the running version is whatever `kustomization.yaml` says, and a release is a commit.

The backend runs as a fixed non-root UID, with a read-only root filesystem, all capabilities
dropped and no service account token.

## Alternatives considered

**Mount the node's `tailscaled` socket with `hostPath`.** This needed no code change. It lost
because it grants write access to the node's Tailscale configuration to a pod that only reads,
and because it makes the pod depend on the node it is scheduled on.

**Run a Tailscale sidecar in the pod with its own identity.** The pod would join the tailnet as
its own device and could read peer status locally. It lost because it adds a device per pod and
needs an auth key, which is a stronger credential than a read-only API client. It also changes
what Nexus displays, since the sidecar would appear as a node of its own.

**Build images on the node and import them with `k3s ctr images import`.** This is faster to set
up and needs no registry. It lost because it is a manual step with no record of which commit is
running, and because it does not survive the node being rebuilt.

**Keep Nexus on Docker Compose.** It already worked. It lost because it leaves the cluster with
no application workload, which is the gap this ADR exists to close.

## Consequences

- Nexus depends on Tailscale's control plane being reachable. If the API is down, the topology
  endpoint fails. The local socket did not have this dependency.
- The OAuth client secret has to be rotated by hand. Nothing alerts before it is revoked or
  removed.
- A release takes two commits: one that changes the code, which builds the images, and one that
  bumps the tags in `kustomization.yaml`. GitOps (Argo CD) is the planned next step and would
  make the second commit the only deploy action.
- The frontend still runs the stock nginx image, which starts as root. Moving it to an
  unprivileged image on a high port is a known follow-up.
- `docker-compose.yml` remains for running the full stack on one host. It is no longer the
  deployment.
