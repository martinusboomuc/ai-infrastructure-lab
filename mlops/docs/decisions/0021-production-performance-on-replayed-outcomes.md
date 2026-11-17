# ADR-0021: Measure production performance on replayed outcomes, with a simulated delay

**Status:** Accepted; point 4 superseded by [ADR-0022](0022-publish-known-performance-state-on-every-run.md)
**Date:** 2026-11-16

## Context

Drift (ADR-0015, ADR-0018) says whether inputs or scores moved. It cannot say whether the model
is still right. That needs outcomes, and a credit outcome is known only once the loan has had
time to default.

`bankml.monitoring.delayed_performance` existed since Phase 5 but had never produced a number:
- **The maturity window is 540 days.** It counted a prediction only once 540 days had passed,
  so nothing served by this project would qualify for 18 months.
- **It read outcomes from the processed feature set on local disk.** That file exists on
  `docker-01` only. A scheduled job on k3s, like drift, has no copy.

The replayed traffic (ADR-0016) changes what is possible. Every replayed request is a real
held-out test applicant, sent with its `SK_ID_CURR` as `applicant_id`, and Home Credit records
whether each one defaulted. About 1,200 replayed predictions were already in the log on
2026-11-16.

## Decision

1. **Outcomes come from a feed, not from the feature set.**
   - `python -m bankml.monitoring.outcomes` runs on `docker-01` after the replay requests are
     built.
   - It writes `applicant_id,outcome` for the replayed applicants only, to
     `replay/<domain>/outcomes.csv`, next to the requests.
   - This stands in for a bank's loan servicing system. The job reads it the way it would read
     that system's outcome table.
2. **A replayed prediction's outcome counts as known `label.replay_outcome_delay_days` (7) after
   it was served.**
   - This is a simulation of `label.maturity_days`, stated as one in the config, the job and this
     ADR.
   - Live traffic has no outcome feed and is not measured.
3. **The job measures the production version only, in a window.**
   - It counts predictions served between 37 and 7 days ago (`window_days` 30 plus the delay).
   - As with drift (ADR-0018), a promotion starts the measurement again for the new version,
     rather than mixing two models' predictions.
4. **It reports enough to judge the model, and measures only when there is enough data.**
   - **Metrics:** ROC-AUC, PR-AUC, recall and precision of the logged decisions, alert rate,
     positive rate and the confusion counts.
   - **Minimum sample:** at least 500 predictions with outcomes and 25 defaults. Below that it
     reports `insufficient_outcomes` and pushes only a heartbeat.
5. **It alerts on ROC-AUC against the version's own test ROC-AUC.**
   - A drop above 0.05 fires a Grafana warning. That is the same size as the slice tolerance
     (ADR-0020).
   - ROC-AUC is the comparison because it does not depend on a threshold or on the base rate.
   - PR-AUC and recall are reported beside it.
6. **It runs daily on k3s.** The `performance-credit` CronJob runs at 06:30, from the serving
   image.
   - It logs a run to `bankml-<domain>-monitoring` and pushes `bankml_performance_*` gauges to
     the Pushgateway.
   - A second rule alerts when no heartbeat has arrived for 2 days.

## Alternatives considered

**Keep the 540-day maturity and wait.**
- It lost because nothing would be measured within the life of this project. The monitoring path
  would stay untested until then.

**Treat an outcome as known as soon as the prediction is logged.**
- It lost because it hides the defining property of credit monitoring: performance always lags
  the decision.
- A delay, even a short one, keeps the window logic, the waiting period after a promotion and the
  `insufficient_outcomes` state real.

**Mount the processed feature set into the k3s job.**
- It lost because it would put the full data set, with its redistribution terms, on another host
  for the sake of two columns of 5,000 rows.

**Alert on PR-AUC or recall.**
- They lost because both move with the base rate and the threshold. A replay window with a few
  more defaults than usual would look like a better or worse model.
- They are reported, not alerted on.

## Consequences

- **The question "how good is the model in production" now has an answer every day.** It is in
  MLflow, in Prometheus, and in an alert.
- **The answer starts late after each promotion.** The replay sends 200 predictions a day. A new
  version needs 7 days for outcomes plus about 3 days of traffic to reach 500, so roughly 10
  days. The first scheduled measurement of v3, promoted on 2026-11-16, is due around 2026-11-26.
- **Replayed traffic comes from the test split.** A live result close to test is expected, and
  says the serving path reproduces training. It does not show the model holding up on a new
  population; nothing in this project can, because the data is static.
  - The first measurement, of v1 on 1,201 predictions with the delay set to 0 by hand, gave
    ROC-AUC 0.782 against 0.762 on test.
- **The replay wraps around after 5,000 requests**, about 25 days. Later windows reuse
  applicants, which is fine for a ranking metric but means the sample is never larger than
  5,000.
- **The old maturity-based path is removed.** `label.maturity_days` still decides which training
  rows are mature (ARCHITECTURE.md section 3).
