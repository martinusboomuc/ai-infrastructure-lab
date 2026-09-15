# ADR-0006: Defer the feature store

**Status:** Accepted
**Date:** 2026-09-15

## Context

A feature store was listed as a core platform module in the original plan. Feature stores solve
three problems: reuse of feature definitions across teams, point-in-time-correct historical
retrieval for training, and low-latency online serving of the same features with guaranteed
offline/online parity.

Examined against this project's actual situation: there is one team and initially one domain, so
reuse across teams is not a live problem. Point-in-time correctness is required, but it is a
property of the feature *code*, enforced by the leakage test in
[ADR-0004](0004-temporal-validation.md), and a store does not supply it for free. Offline/online
parity is a genuine risk, and is addressed structurally by having training and serving import the
same feature module.

Feast without an online store — Redis or equivalent — is a metadata registry over Parquet files.
With one, it is an additional stateful service to deploy, secure, monitor and pay for.

## Decision

No feature store in Phases 2–6. Point-in-time-correct feature construction is implemented
directly in `src/bankml/features/`, with the as-of contract enforced by the CI leakage test.
Training and serving import the same module.

Feast is reconsidered after Phase 6, and only if a concrete offline/online skew problem has
actually appeared.

## Alternatives considered

**Feast with an offline store only.** Rejected: adds a registry and a configuration surface while
solving nothing that the feature module does not already solve, and would let "we have a feature
store" stand in for the harder work of getting point-in-time correctness right.

**Feast with Redis online.** The full, honest version. Deferred rather than rejected — it is the
right answer once low-latency serving of precomputed aggregate features is a real requirement.
Building it before that requirement exists means operating a stateful service to demonstrate a
capability nothing needs yet.

**A hand-rolled online feature cache.** Rejected: the worst of both — operational burden without
the standard tooling, semantics or ecosystem.

## Consequences

- One fewer service to deploy and pay for; Phase 4 stays inside Container Apps and Blob Storage.
- The leakage test carries the full weight of point-in-time correctness. It has to be right.
- Features are recomputed at request time in serving rather than looked up. Acceptable for a
  synchronous credit decision; it would not be for a sub-100ms transaction authorisation, which
  is precisely the trigger for revisiting this.
- "Feature Store" is removed from the platform module list and appears in the roadmap under
  *Later*, with the condition that would justify it stated explicitly.
