# ADR-0018: Measure drift over the last seven days, on the production model's own predictions

**Status:** Accepted
**Date:** 2026-11-15

## Context

The drift job (ADR-0015) compared the training population against every prediction ever
logged. Two things made that wrong once traffic existed (ADR-0016).

**Time.** The replay adds 200 predictions a day.
- After a month, a shift that began this week would be about a fifth of the comparison, so its
  PSI would be diluted below the threshold by older, unshifted traffic.
- The longer the job ran, the less able it was to notice change.
- Reading the whole log also grew with its age, because every day file was downloaded on every
  run.

**Model version.** Prediction drift compares the production model's scores on its training
population against the scores in the log.
- After a promotion, the log still holds the previous model's scores.
- Comparing them would report the change of model as drift, and would trigger a retrain for it.
- Every logged record already carries `model_version`.

## Decision

1. **Read only the last seven days** (`DEFAULT_WINDOW_DAYS`, overridable with `--window-days`).
   - Seven days of the daily replay is about 1,400 records, above the 500 the job requires
     (`DEFAULT_MIN_CURRENT`). A week is also short enough that a shift dominates the comparison
     within days.
   - `read_all_records(domain, since=...)` skips day files dated before the window, locally and in
     Blob, so the cost of a run no longer grows with the log.
   - It then keeps only records whose `timestamp` falls inside the window.
2. **Read only predictions made by the current `<domain>-champion@production` version.**
   - The job resolves the alias first, then filters on `model_version`.
   - Right after a promotion, a run reports `no_data` until the new model has served 500
     predictions inside the window. That is correct: there is nothing yet to judge the new model
     on.
3. **Record the window.**
   - `window_days`, `window_start` and `model_version` are part of every result, including
     `no_data`.
   - They are logged as MLflow params of the drift run, so each historical result says what it
     was computed on.

Verified on the real log on 2026-11-15:
- The 7-day window held 1,000 predictions, all by v1. The 2 records from September fell outside
  it.
- The result matched the earlier all-time run: no drift, highest feature PSI 0.076, score PSI
  0.015.

## Alternatives considered

**Keep all-time, and lower the PSI threshold to compensate for dilution.**
- It lost because the dilution keeps growing, so no fixed threshold stays right.
- A lower threshold also fires on noise early on, when the log is small.

**A fixed number of most recent predictions, for example the last 2,000.**
- The sample size would be constant.
- It lost because its time span depends on traffic volume: a quiet month and a busy day would
  look the same.
- Time is also how the result is read: "drift in the last week".

**Compare consecutive windows (this week against last week) instead of against training.**
- It catches sudden change sharply.
- It lost as a replacement because a slow drift never shows between neighbouring weeks, and the
  question this job answers is whether the world has moved since the model was trained.
- It could be added later as a second comparison.

## Consequences

- **A shift is judged on recent traffic.** One that starts on a given day dominates the window
  within about a week, instead of being averaged against everything before it.
- **Runs no longer slow down as the log grows**, because only the window's day files are read.
- **A promotion opens a gap.** Drift on the new model reports `no_data` until it has 500
  predictions, about three days of replay. The staleness alert is unaffected, because a `no_data`
  run still pushes its heartbeat.
- **A day without traffic is invisible.** The window shrinks, but the job only notices when the
  count drops below 500.
- **The delayed-label performance job still reads the whole log.** It needs every prediction
  whose label has matured, not a recent window.
