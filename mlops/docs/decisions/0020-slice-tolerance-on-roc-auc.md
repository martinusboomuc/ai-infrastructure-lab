# ADR-0020: Measure slice tolerance on ROC-AUC, not PR-AUC

**Status:** Accepted
**Date:** 2026-11-16

## Context

The promotion gate (ADR-0005, `bankml.registry.gate`) fails a champion when any configured
slice falls more than `tolerance` (0.05) below the overall figure on test. Until now that figure
was PR-AUC.

The check is meant to catch a model that ranks one group worse than the rest. PR-AUC does not
measure that alone: it also moves with the slice's positive rate. A random model's PR-AUC
equals the base rate, so a group with fewer defaults has a lower PR-AUC even when the model
ranks it exactly as well.

That is what blocked every Credit Risk champion since Session 005. The scorecard on the
2026-11-16 test split shows it:

| Slice | n | Default rate | ROC-AUC | PR-AUC |
|---|---|---|---|---|
| Overall | 32,743 | 7.9% | 0.7469 | 0.2236 |
| `NAME_EDUCATION_TYPE = Higher education` | 8,053 | 5.1% | 0.7399 | 0.1358 |

- **PR-AUC fell 0.088,** outside the tolerance, so the gate failed.
- **ROC-AUC fell 0.007.** The model ranks that group as well as the others.
- **PR-AUC over the base rate** is 2.7x on the slice and 2.8x overall, which agrees with
  ROC-AUC.

The gate was flagging the slice's default rate, not the model. ADR-0019 recorded this and left
the decision open.

## Decision

1. **Slice tolerance applies to the drop in ROC-AUC** against overall. The column list and the
   0.05 tolerance in `configs/<domain>.yaml` are unchanged.
2. **Every slice still reports its PR-AUC, with its positive rate and size**, in
   `slice_metrics.json` and in the model card. Nothing is dropped, so the reader can still see
   where precision is lower and why.
3. **The model-level gate is unchanged.** It still requires a test PR-AUC floor (ADR-0005), and
   promotion still compares test PR-AUC against production (ADR-0019). ROC-AUC decides only the
   comparison between groups, where the base rates differ.

## Alternatives considered

**Keep PR-AUC and raise the tolerance.**
- It lost because the tolerance would then depend on how far a slice's base rate is from the
  average. That is a property of the data, not a measure of fairness, and it would hide a real
  degradation on a slice whose base rate is close to the overall rate.

**Compare PR-AUC lift over each slice's base rate.**
- It removes most of the base-rate effect, and the numbers above agree with ROC-AUC.
- It lost because it is not a standard measure. Each reader would need it explained, and its
  tolerance has no common reference point.

**Keep the check and promote by hand each time.**
- It lost because a check that always fails is ignored. It would have stopped blocking anything
  in practice while still appearing in the gate.

## Consequences

- **The scorecard now passes the gate on test.** Every slice is within 0.01 ROC-AUC of overall.
- **Production does not change on this alone.**
  - The scorecard's test PR-AUC (0.2236) is more than 0.005 below v1's (0.2418), so ADR-0019
    leaves it as `candidate`.
  - Moving production to the explainable champion is now a documented human decision:
    `python -m bankml.registry.promote --domain credit --version <n>`.
- **Small slices are noisy, and this does not fix that.**
  - On validation, `Incomplete higher` (1,722 rows, about 145 defaults) is 0.052 below overall.
    On test (1,089 rows) it is 0.011 above.
  - The gate reads test only, so this is reported, not blocking.
  - A minimum slice size, or a confidence interval on the drop, is the next refinement if it
    starts to decide outcomes.
- **ROC-AUC does not see a group whose scores are shifted** while its ranking stays intact. That
  is calibration by group. It is visible in the calibration figure ADR-0019 logs, but no gate
  checks it per slice.
- **The CLAUDE.md rule that "ROC-AUC alone is never a promotion gate" still holds.** ROC-AUC is
  one check among the PR-AUC floor, the production comparison, reason codes and the model card.
