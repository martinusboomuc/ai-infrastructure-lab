# Architecture Decision Records

Every choice with a defensible alternative is recorded here. The value is not the decision — it
is the alternative that was rejected and the reason it lost.

Decisions are immutable once accepted. A changed mind produces a **new** ADR that supersedes the
old one; the old one stays, marked as superseded.

## Index

| # | Decision | Status |
|---|---|---|
| [0001](0001-repo-placement.md) | BankML lives inside `ai-infrastructure-lab/mlops` | Accepted |
| [0002](0002-vertical-slice-first.md) | Build one domain end-to-end before adding a second | Accepted |
| [0003](0003-pandera-over-great-expectations.md) | Pandera for data validation | Accepted |
| [0004](0004-temporal-validation.md) | Temporal splits, label maturity, and a CI leakage test | Accepted |
| [0005](0005-scorecard-champion-gbm-challenger.md) | Logistic scorecard is champion for Credit Risk | Accepted |
| [0006](0006-defer-feature-store.md) | Defer the feature store | Accepted |
| [0007](0007-synthetic-fixtures-for-leakage-test.md) | Synthetic fixtures for the CI leakage test | Accepted |

## Template

```markdown
# ADR-NNNN: <title>

**Status:** Proposed | Accepted | Superseded by [ADR-NNNN](...)
**Date:** YYYY-MM-DD

## Context
What situation forces a decision. Facts and constraints, no conclusions.

## Decision
What was decided, stated in the active voice.

## Alternatives considered
Each option, and the specific reason it lost.

## Consequences
What this makes easier, what it makes harder, and what it commits us to.
```
