# Architecture Decision Records

Lab-wide decisions — infrastructure, networking, conventions that apply across projects. See
`mlops/docs/decisions/` for BankML-specific decisions; that series is independent (ADR-0001
there scopes BankML as its own project root precisely so the two series don't collide).

Every choice with a defensible alternative is recorded here. The value is not the decision — it
is the alternative that was rejected and the reason it lost.

Decisions are immutable once accepted. A changed mind produces a **new** ADR that supersedes the
old one; the old one stays, marked as superseded.

## Index

| # | Decision | Status |
|---|---|---|
| [0001](0001-hybrid-infrastructure.md) | Hybrid infrastructure: homelab for self-hosted services, cloud for managed ones | Accepted |

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
