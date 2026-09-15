# ADR-0002: Build one domain end-to-end before adding a second

**Status:** Accepted
**Date:** 2026-09-15

## Context

The original plan proposed five banking domains — fraud, credit, AML, churn, marketing — each
running a full MLOps lifecycle, alongside eleven platform modules including a feature store, a
data catalogue, a dashboard and user management.

The observable failure mode for projects of this shape is well known: an elaborate README over a
repository containing a training notebook and a `Dockerfile`. For a portfolio artifact this is
worse than doing less, because a reader who compares the claims to the code concludes the author
overpromises.

There is also a technical argument. The claim "this architecture is domain-agnostic" is only
credible if it is *tested*, and it cannot be tested by building five domains simultaneously —
that produces five parallel implementations that merely resemble each other.

## Decision

Build the complete platform on **Credit Risk** first. Every layer must work end-to-end for that
one domain before a second is started. Then add **Fraud Detection**, and treat the size and shape
of that pull request as the evidence for the domain-agnosticism claim.

The README states plainly what exists and what is planned, and that table is updated with every
merged change.

## Alternatives considered

**All five domains in parallel.** Rejected: maximises surface area before any layer is proven,
and every core change must then be applied five times.

**Two domains from the start, to force generality early.** Genuinely tempting — it prevents
baking Credit Risk assumptions into the core. Rejected because generalising from two concrete
implementations is more reliable than designing for generality up front, and the refactor it
implies is itself a worthwhile, reviewable artifact.

**Breadth-first: all five domains, training only, MLOps later.** Rejected: this is exactly the
"five notebooks in a folder" outcome the project exists to avoid.

## Consequences

- The repository will look narrow for several months. The status table makes that legible as
  discipline rather than abandonment.
- The core will initially carry Credit Risk assumptions. Phase 6 is expected to require a
  refactor, and that refactor is a feature of the plan, not a defect in it.
- Churn and Marketing enter early but only as CI fixtures, which costs little and keeps the
  pipeline honest.
- The Phase 6 exit criterion is falsifiable: if adding Fraud touches core code, the claim was
  wrong and the core gets fixed.
