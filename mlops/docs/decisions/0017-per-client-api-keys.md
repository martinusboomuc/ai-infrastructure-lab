# ADR-0017: Require a per-client bearer key on the prediction and metrics endpoints

**Status:** Accepted
**Date:** 2026-11-15

## Context

The serving API on Azure Container Apps (ADR-0012) has a public ingress and no authentication.
Anyone who finds the URL can do two things:

- call `/predict/credit`, which writes every request into the prediction log;
- read `/metrics`.

The drift job and the delayed-label performance job treat that log as production traffic. Since
ADR-0016, the log also mixes real and replayed requests, told apart only by a header the caller
sets itself. An unauthenticated caller can therefore skew drift, fill Blob storage, and claim to
be either kind of traffic.

The API has three known callers:

- **The replay CronJob on k3s** posts predictions.
- **Prometheus on `monitoring-01`** scrapes `/metrics`.
- **The owner, testing by hand,** calls either.

Container Apps' platform probes and Nexus only read `/health`.

## Decision

1. **Use bearer keys, one per named client.**
   - `BANKML_API_KEYS` holds `name:key` pairs and is set from a Container App secret.
   - `bankml.serving.auth` checks `Authorization: Bearer <key>` in constant time against every
     configured key.
2. **Protect `/predict/credit` and `/metrics`.** `/health` and the OpenAPI docs stay open, because
   they carry nothing private and the platform probes depend on them.
3. **Record who made each call.** The prediction log gains a `client` field with the caller's
   name. It is set by the server from the key, not claimed by the caller like
   `traffic_source` is.
4. **Fail closed.**
   - With no keys configured, protected endpoints answer 503.
   - A malformed key list stops startup: a missing separator, a duplicate name, or a key shorter
     than 32 characters.
5. **Give each client its own key and its own store.**
   - The replay job reads `BANKML_API_KEY` from the k3s Secret `bankml-api-key`.
   - Prometheus reads a `credentials_file` on `monitoring-01` (`monitoring/secrets/`, gitignored).
   - Revoking one client is a matter of removing its pair from the Container App secret.

## Alternatives considered

**Container Apps built-in authentication with Microsoft Entra ID.**
- Tokens would be issued and validated by the platform, with no key handling in the app.
- It lost because both machine callers would need an Entra app registration and a client secret
  anyway, plus a token exchange before every run.
- Prometheus cannot perform an OAuth client-credentials flow without a sidecar.
- The subscription is Azure for Students, where app registrations have been unreliable
  (ADR-0011).

**Put the API behind Cloudflare Access, like MLflow.**
- The same service-token pattern would already be familiar.
- It lost because it would move the public endpoint onto the homelab's Cloudflare domain and
  route Azure-hosted traffic through a third party for a service that already has its own
  ingress.

**One shared key for every caller.**
- It is simpler.
- It lost because revoking it breaks every caller at once, and the log could not say who made a
  request.

**Restrict ingress by IP address.**
- It lost because the homelab's public address is residential and changes.
- It also says nothing about which caller made a request.

## Consequences

- **The log can be trusted to come from known callers.** A third party can no longer write into
  it, and every record names its client.
- **Keys exist and must be managed.** They are generated once, held in three places (the
  Container App secret, the k3s Secret, and the file on `monitoring-01`), and rotated by hand.
  Nothing alerts when a key leaks.
- **Rollout has an order.**
  - The keys must exist everywhere before the image that enforces them deploys. Otherwise
    replay fails with 401 and the Prometheus target goes down.
  - The CronJobs then need the new image, because the replay job only sends its key from that
    image on.
- **Manual calls need a key.** The OpenAPI docs page has an Authorize button for it.
- **Not covered:** rate limiting, key expiry, and per-client permissions. Every key can call every
  protected endpoint.
