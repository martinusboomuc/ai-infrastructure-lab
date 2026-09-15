# ADR-0004: Temporal splits, label maturity, and a CI leakage test

**Status:** Accepted
**Date:** 2026-09-15

## Context

Fraud and credit datasets are time-ordered, and the production task is always to predict
*forward*. Two standard practices from general ML break badly here:

**Random cross-validation** places future rows in the training fold. With entity-level
correlation — the same customer, card or merchant appearing on both sides of the split — the
model memorises entities rather than learning the signal. The reported metric is inflated, often
substantially, and the inflation is invisible without a temporal holdout.

**Aggregating relational history naively.** Home Credit's bureau, previous-application and
instalment tables are keyed by customer, not by application date. A plain `GROUP BY customer_id`
silently includes records that postdate the decision being modelled. The resulting feature
encodes the outcome.

**Label maturity** compounds both. A credit default label needs 12–24 months to be trustworthy.
Recent applications labelled "no default" are largely unresolved cases, not negatives.

These are the errors that most distinguish production banking ML from competition ML, and all
three are silent — nothing crashes, the metrics simply lie.

## Decision

Enforce three rules in the platform, not in the modeller's discipline:

1. **Chronological splits with an explicit gap window**, configured per domain. Random splitters
   from `sklearn` are banned in `src/` by a lint rule.
2. **Label maturity windows.** Rows more recent than `now - maturity_days` are excluded from
   training, per domain config.
3. **A leakage test in CI.** For held-out rows, features are built twice — once against the full
   relational tables, once against the tables truncated at that row's decision timestamp — and
   the two feature vectors must be identical. A feature that fails cannot be merged.

## Alternatives considered

**Convention and code review only.** Rejected: these errors are silent, and a reviewer cannot see
a leaking aggregation by reading a diff. An automated check is the only reliable defence.

**Grouped/entity-aware cross-validation.** Solves entity overlap but not temporal ordering, and
does nothing about relational-history leakage. Strictly weaker than a temporal split here.

**Trusting a feature store to guarantee point-in-time correctness.** Correct in principle, but
a feature store is deferred ([ADR-0006](0006-defer-feature-store.md)), and the guarantee still
requires the same as-of discipline in the feature code. The test is what actually enforces it;
the store would merely be a convenient place to put it.

## Consequences

- Reported metrics will be **lower** than published Kaggle leaderboard scores on the same
  datasets. This is correct, and the gap is documented rather than hidden.
- Feature engineering becomes meaningfully harder: every aggregation takes an explicit as-of
  timestamp, and the leakage test will reject convenient shortcuts.
- Less training data is usable, because the maturity window removes the most recent rows.
- The monitoring layer cannot compute live performance immediately. Drift is measured now;
  performance is measured later, when labels mature.
- The leakage test becomes the single most important test in the suite. If it is ever disabled
  to unblock a merge, the project's central claim is void.
