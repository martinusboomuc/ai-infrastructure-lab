# ADR-0019: MLflow conventions, evidence on every version, and promotion against production

**Status:** Accepted
**Date:** 2026-11-16

## Context

On 2026-11-16 the MLflow server held six experiments: `Default`, `credit-risk`, `credit-risk-v2`,
`credit`, `credit-monitoring` and `fraud`.
- Three runs had failed. Eight runs in `credit` were four identical champion and challenger
  pairs.
- No run had been made since September.

Nothing in it answered "how good is the model in production":
- **The production version said nothing about itself.** `credit-champion` v1 had no
  description and no tags.
- **There were no figures.** Runs held numbers only: no curves, no calibration, no confusion
  matrix.
- **There was no data lineage.** Runs carried a hash of `dvc.lock` as a tag but no inputs.

The production version also turned out not to be what the registry name says.
- Its source run is `role=challenger`, `model_type=lightgbm`, in `credit-risk-v2`. That is the
  experiment someone created by hand on 2026-09-21 to work around the artifact-location bug
  ADR-0014 describes.
- It was registered and aliased by hand, not by the pipeline. It never passed the gate.
- ADR-0005 names the scorecard as the Credit Risk champion.

Running the current pipeline on the same data showed two more problems.
- **The gate blocks the scorecard.** It fails on the `NAME_EDUCATION_TYPE = Higher education`
  slice.
- **Promotion was absolute.** Any champion that passed the floor would have replaced
  production, even with a lower PR-AUC (0.224 against v1's 0.242).

## Decision

1. **One naming scheme for experiments:** `bankml-<domain>-<purpose>`, where `purpose` is
   `training` or `monitoring` (`bankml.tracking.experiment_name`). Training, drift and delayed
   performance all use it.
2. **Every training run carries its evidence.**
   - **Provenance tags:** `domain`, `role`, `model_type`, `git_sha`, `git_dirty` and
     `dvc_data_version`.
   - **A description** with the test metrics.
   - **Evaluation settings** as params.
   - **Rows and positive rate** per split.
   - **The train, validation and test sets as run inputs.** Their digest is the DVC data
     version.
   - **Five figures each for validation and test**, under `figures/<split>/`: ROC,
     precision-recall, calibration by score decile, confusion matrix at the alert threshold, and
     score distribution by outcome (`bankml.evaluation.plots`).
3. **Every gated champion is registered,** with tags for its test metrics, run, data and code
   version, and gate result, plus a description. The `candidate` alias points at the newest one.
4. **Promotion compares against production.**
   - A candidate whose test PR-AUC is at most `evaluation.gate.max_pr_auc_regression` (0.005)
     below production's is promoted automatically.
   - Otherwise it stays `candidate`. Promoting it is a person's decision:
     `python -m bankml.registry.promote --domain <domain> --version <n>`.
   - The version that `production` leaves is kept as `previous-production`, so a rollback is one
     alias change.
5. **No model signature.** pyfunc enforces a logged signature on every `predict` call. The
   categorical dtypes serving builds per request do not round-trip through MLflow's schema types,
   so a signature would break serving. Inputs are recorded through the run's dataset inputs
   instead.
6. **The existing history is reorganized, not rewritten.**
   - `credit`, `credit-monitoring` and `fraud` are renamed to the new scheme.
   - `credit-risk-v2` is renamed to `bankml-credit-training-2026-09` and kept while v1 is in
     production, because v1's run and its drift reference live there.
   - `credit-risk`, the runs in `Default`, and the duplicate runs in `credit` are deleted. This
     is MLflow's soft delete, so it can be reversed.
   - v1 gets the same tags and description a new version would, including how it was
     registered.

## Alternatives considered

**Keep promoting on the gate alone.**
- It lost because the gate is a floor. Passing it says a model is acceptable, not that it is
  better than the one serving.

**Promote only by hand.**
- It lost because a retrain that is at least as good would then wait on a person for no reason.
- Automatic promotion within a tolerance, and a person deciding otherwise, keeps both.

**Use MLflow's built-in `mlflow.evaluate` for figures and metrics.**
- It produces similar plots.
- It lost because it computes its own metric set, which would then disagree with the
  cost-sensitive metrics the gate and the model card use (`bankml.evaluation.metrics`).
- One set of numbers is the point.

**Delete all old experiments, including `credit-risk-v2`.**
- It lost because deleting the experiment deletes v1's source run, and the drift job reads its
  reference population from that run (ADR-0015).

## Consequences

- **The run page answers the questions.** It shows how good a model is, on what data, from
  which code, and with figures that show why.
- **The registry page compares versions** from their tags, without opening runs.
- **A worse model can no longer replace a better one silently.**
- **A retrain today does not change production.** The gate blocks the scorecard on the
  education slice, so v1 stays.
  - That slice check compares PR-AUC across groups with different default rates: 5.1% for
    Higher education against 7.9% overall.
  - PR-AUC falls with the base rate even when ranking quality is the same. On test, the
    scorecard's PR-AUC over the base rate is 2.7x on that slice and 2.8x overall.
  - Whether the slice check should change is a separate decision, not taken here.
- **v1 is documented as it is:** a LightGBM challenger registered by hand, which would fail the
  same slice check.
- **`matplotlib` becomes an explicit dependency.** It was already installed through `shap`.
