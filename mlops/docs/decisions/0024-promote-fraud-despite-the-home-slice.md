# ADR-0024: Promote the Fraud champion despite the `home` slice, through a recorded override

**Status:** Accepted
**Date:** 2026-11-25

## Context

The first Fraud champion on 30-day features (ADR-0023) failed the gate on five merchant
categories. The gate requires each slice's test ROC-AUC to be within 0.05 of the overall test
ROC-AUC (ADR-0020). Travel was the worst, at 0.747 against 0.946.

Part of that gap is the comparison itself, not the model.
- Fraud rates differ widely by category, so the category alone separates much of the fraud.
- The overall ROC-AUC counts those easy pairs across categories. A slice ROC-AUC has only pairs
  within one category.
- A slice therefore sits below overall even for a model that ranks well everywhere.

Part of it was a real weakness. Travel at 0.747 is far below what sampling noise explains with
37 frauds. The model could not tell an unusual travel purchase from a usual one, because it knew
nothing about the card's own habits in a category.

One modelling change followed, chosen for that reason and not to pass a slice. Three features
compare a transaction with the card's last 30 days, overall and in its category (ADR-0023). On
test, a dry run gave:

| | Before | After |
|---|---|---|
| PR-AUC | 0.693 | 0.708 |
| ROC-AUC | 0.946 | 0.964 |
| Recall at a 1% alert rate | 0.909 | 0.936 |
| Expected cost | 12,618 | 10,323 |
| travel ROC-AUC | 0.747 | 0.930 |
| Slices outside tolerance | 5 | 1 |

`home` alone still fails: 0.811 on test with 63 frauds, and 0.893 on validation with 46. Both are
more than 0.05 below overall.

The gate reads the test split. Changing features again until `home` passes would select the
model on test, and the test numbers would stop meaning what they claim. A failed champion is not
registered, so promoting it needs a path the registry did not have.

## Decision

1. **The Fraud champion trained on the ADR-0023 features is promoted with `home` below
   tolerance.**
2. **Overriding the gate is a recorded act, not a silent one.**
   - The training pipeline now tags every champion run `gate=passed` or `gate=failed`, and adds
     the gate's reasons as `gate_reasons`.
   - `python -m bankml.registry.promote --run-id <id> --reason "<why>"` registers only a run
     tagged `gate=failed`, and refuses an empty reason.
   - The version carries `gate=failed`, the gate's reasons, `promotion=promoted by hand despite
     the gate: <reason>`, the run's provenance tags, and the reason in its description.
   - It becomes `candidate` and `production`; the version it replaces stays `previous-production`.
3. **No further feature changes are judged on test for this model.** The next iteration is
   selected on validation and read on test once.

## Alternatives considered

**Keep iterating until `home` passes.**
- It lost because each iteration chosen by looking at test slices spends the test split. With 63
  frauds in `home`, a pass after several attempts would say more about the attempts than about
  the model.

**Change the slice rule for Fraud.** For example, compare each category with the mean ROC-AUC
within categories instead of the pooled ROC-AUC.
- It is the better rule for a slice column that is itself predictive, and it may be adopted
  later.
- It lost for now because changing a gate rule while the model it would pass is in hand is the
  kind of decision a gate exists to prevent. It needs its own ADR, applied to the next model.

**Do not serve Fraud until a model passes.**
- It lost because the model is better than the one it would wait for on every measure but one
  slice, and the weakness is known and written down. Serving it is also how its behaviour on
  `home` gets measured.

**Drop `category` from Fraud's slices.**
- It lost because it removes the check that found the travel weakness.

## Consequences

- **The Fraud production version says, in the registry, that it failed the gate and why.**
  Nexus and the model card can show this instead of a plain "production".
- **`home` is the known weak category.** Per-category performance in production is the
  follow-up that would show whether it holds. The performance job (ADR-0021) does not slice yet.
- **The LightGBM uses default parameters**, and with 0.5% positives some leaves reach extreme
  values. The base log-odds is about -647, where a calibrated model would sit near -5.
  - Ranking is unaffected.
  - SHAP reason codes are exact (they add up to the raw score) but run into the hundreds, and
    the scores are not calibrated probabilities.
  - Regularizing the leaves (`min_child_weight`, `reg_lambda`) is the first change for the next
    iteration, judged on validation.
