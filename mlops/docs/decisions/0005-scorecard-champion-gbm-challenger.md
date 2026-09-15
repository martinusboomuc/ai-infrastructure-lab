# ADR-0005: Logistic scorecard is champion for Credit Risk

**Status:** Accepted
**Date:** 2026-09-15

## Context

The original plan treated logistic regression as a disposable baseline in every domain, with a
gradient boosting model as the production model throughout. For fraud detection that is correct.
For credit risk it inverts how the industry actually works.

Consumer lending decisions must be explained to the applicant — a declined applicant is entitled
to the principal reasons — and defended to internal model validation and supervisors under model
risk management practice. The long-standing answer is the **scorecard**: weight-of-evidence
binning followed by logistic regression, producing an additive, monotonic, points-based model
where every contribution is directly attributable.

Gradient boosting reliably scores better on discrimination. It also produces a model whose
explanations are post-hoc approximations rather than the model's own structure.

## Decision

For **Credit Risk**, the WoE + logistic scorecard (via `optbinning`) is the **champion** and
LightGBM is the **challenger**. Both are trained on every run, both are evaluated under the same
gate, both produce reason codes, and the comparison itself is a reported artifact.

For **Fraud Detection**, the assignment reverses: LightGBM is champion, logistic regression is
the baseline. There is no adverse-action requirement on a blocked transaction comparable to a
declined loan, and the imbalance and interaction structure strongly favour a GBM.

## Alternatives considered

**LightGBM as champion everywhere.** Simpler and scores better. Rejected: it models the
optimisation problem while ignoring the constraint that actually shapes credit modelling, and it
forfeits the most interesting thing the project can demonstrate.

**Scorecard only for credit, no GBM.** Rejected: the cost of the constraint is the finding. Not
measuring the discrimination given up would waste the exercise.

**GBM with monotonic constraints as a compromise.** A real option, and closer to some current
practice. Deferred rather than rejected — it belongs as a *second* challenger once the
champion/challenger machinery exists, and is noted in the roadmap.

## Consequences

- The credit pipeline carries two model families, so the training code must be model-agnostic
  from the start. That pressure is useful.
- `optbinning` becomes a dependency, and WoE binning must itself respect the temporal split —
  bins are fit on training data only.
- The evaluation gate must compare champion against challenger on discrimination *and* record
  the explainability asymmetry, rather than promoting on a single metric.
- The project gains a defensible answer to an interview question that GBM-everywhere cannot
  answer: what a bank gives up for explainability, measured rather than asserted.
