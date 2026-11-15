# ADR-0007: Sync the k3s workloads from Git with Argo CD

**Status:** Accepted
**Date:** 2026-11-15

## Context

`k8s-01` runs two workloads from Kustomize manifests in this repository:

- Nexus (`nexus/deploy/k8s`, ADR-0003);
- BankML's drift and replay CronJobs (`mlops/deploy/k8s`, mlops ADR-0015 and ADR-0016).

A release was a commit that changed an image tag, and then someone had to apply it.

In practice, that someone applied from the Mac by copying the manifests to the node, because
the clone on `k8s-01` had not been updated since September. On 2026-11-15:

- a release run from the wrong directory reported a successful rollout of the old version;
- a CronJob kept running an image two releases old until it was bumped by hand.

Nothing compared what was running against what Git said should be running.

The cluster is a single node with 3.8 GB of memory shared with the control plane. About 2.5 GB
was free before this change.

## Decision

1. **Run Argo CD v3.5.7 on k3s**, installed from the upstream non-HA manifest, pinned by version
   in `infrastructure/homelab/k3s/argocd/kustomization.yaml`.
   - v3.5.7 is the latest patch of a minor line two weeks old. The 3.6 line was eleven days old.
2. **Use app-of-apps.**
   - One root Application, `homelab`, is applied by hand once.
   - It owns every Application in `argocd/apps/`: `nexus`, `bankml`, and `argocd` itself.
   - Adding a workload to GitOps is a new file in that directory.
3. **Sync automatically, with prune and self-heal**, for the workloads.
   - A commit to `main` reaches the cluster within about three minutes.
   - A change made by hand in the cluster is reverted.
   - The `argocd` Application prunes nothing, so a mistake in its own directory cannot remove
     Argo CD.
4. **Keep hand-made Secrets out of Git and out of Argo CD's view.** They are not part of any
   Application's source (`tailscale-oauth`, `grafana-token`, `azure-storage`, `bankml-api-key`), so
   they are neither tracked nor pruned.
5. **Serve the UI at `http://k8s-01/argocd`** through the existing Traefik ingress, over plain
   HTTP on the LAN and tailnet only, the same exposure as Nexus.
6. **Turn off what is not used.** Dex (single sign-on) and the notifications controller are scaled
   to zero: there is one operator, and alerts already go through Grafana.

## Alternatives considered

**Flux.**
- It is lighter, with no UI or server component, and also a CNCF graduated project.
- It lost because the UI is part of the point here. It shows sync state, drift and history at a
  glance, and Nexus can link to it.
- Argo CD's Application model also maps one to one onto the existing Kustomize directories.

**A CI job that runs `kubectl apply` after each release commit.**
- It needs no new component in the cluster.
- It lost because it would require GitHub Actions to reach a homelab cluster, through a
  self-hosted runner or by exposing the API server.
- It would also still not notice or revert drift between releases.

**Keep applying by hand, and keep the node's clone up to date.**
- It lost because this is the arrangement that had already failed twice in one day.

## Consequences

- **The cluster matches `main`.** A release is one commit, and the UI shows when the cluster does
  not match Git.
- **Changes made by hand do not stick.** A `kubectl edit` to a tracked resource is reverted within
  minutes. Experiments have to go through a branch, or have self-heal paused in the UI.
- **About 600 MB of memory goes to Argo CD** (controller, repo server, API server, Redis). Free
  memory on the node went from about 2.5 GB to 1.9 GB.
- **The cluster now pulls from GitHub and from `raw.githubusercontent.com`** for the pinned
  install. A GitHub outage pauses deploys but does not stop running workloads.
- **The first admin password is in a generated Secret.** It is changed once in the UI, then that
  Secret is deleted. Access is still a single local admin account.
- **Not covered:** `kube-state-metrics` and the k3s node configuration are still applied by hand.
  Image tags are still bumped by a commit rather than by an image-updater.
