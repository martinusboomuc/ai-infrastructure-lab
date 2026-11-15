# ADR-0006: Provision Grafana's contact points and notification policy from files

**Status:** Accepted
**Date:** 2026-11-15

## Context

Grafana on `monitoring-01` gets its datasource, dashboards and alert rules from files in
`infrastructure/homelab/monitoring/grafana/provisioning/`. Two pieces were created through
Grafana's API instead, and lived only in its database volume:

- **The contact points:** the two Discord webhooks, `discord-alerts` and
  `discord-homelab-alerts`.
- **The notification policy** that routes the Homelab folder to the second webhook.

The monitoring README explained why. A committed contact point file seemed to need either the
webhook URL itself, which is a credential, or a placeholder. File-provisioned resources are
reconciled on every start, so a placeholder would silently replace the real URL.

The backups work (ADR-0004) asked what in the lab cannot be rebuilt from the repository. In
Grafana the answer was exactly these two pieces, plus the Nexus service account token. Losing
the volume would leave every alert rule evaluating and firing with nowhere to send it.

## Decision

1. **Provision both from `grafana/provisioning/alerting/notifications.yaml`.**
   - The file reads the webhook URLs from the environment (`$DISCORD_BANKML_WEBHOOK_URL`,
     `$DISCORD_HOMELAB_WEBHOOK_URL`), and they live only in `monitoring-01`'s `.env`.
   - The values were copied there from Grafana's own decrypted export, without being displayed.
2. **Make a missing URL fail loudly.** `docker-compose.yml` passes both with `${VAR:?}`, so Compose
   refuses to start Grafana without them. The placeholder problem can no longer happen silently.
3. **Keep the existing receiver uids**, so provisioning took over the two contact points in place
   rather than creating duplicates.
4. **Tested before switching.** A throwaway Grafana 11.3.0 with the same provisioning directory
   and the real environment came up with:
   - both contact points at `provenance: file`, with the same uids;
   - URLs equal to the `.env` values;
   - the same routing tree.
5. **Do not back up Grafana's database.** After this it holds nothing that cannot be rebuilt from
   the repository and `.env`, apart from the Nexus service account token. That token is recreated
   by hand in a minute.

## Alternatives considered

**Back up the Grafana database volume, like the MLflow registry.**
- It would also cover anything created in the UI later.
- It lost because it preserves the configuration without making it reviewable.
- A restore would also bring back whatever state the database was in, including anything changed
  by hand that nobody remembers.

**Keep the API setup, documented as curl commands in the README.**
- It works for a fresh deploy.
- It lost because the commands carried an outdated copy of the routing tree. Nothing checked that
  the README matched what was running, and recovering depended on someone reading the README.

**Commit the webhook URLs encrypted (SOPS or similar).**
- The whole configuration would be in Git.
- It lost because it adds a key-management tool to the lab for two URLs, while every other
  secret here already lives in a host's `.env`.

## Consequences

- **Rebuildable from the repository.** A fresh `monitoring-01` reproduces alerting exactly from
  the repository and three values in `.env`.
- **Changes to routing go through Git.** Grafana shows provisioned contact points and policies as
  read-only in the UI, so a quick change by hand is no longer possible.
- **Rotating a webhook means editing `.env` and recreating the Grafana container**, not clicking in
  the UI.
- **The unused default `email receiver` contact point stays in the database.** It receives
  nothing, and provisioning does not remove it.
