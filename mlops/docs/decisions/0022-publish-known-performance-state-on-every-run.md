# ADR-0022: Publish what is known on every performance run, not only a heartbeat

**Status:** Accepted
**Date:** 2026-11-17
**Supersedes:** point 4 of [ADR-0021](0021-production-performance-on-replayed-outcomes.md), the
sentence "Below that it reports `insufficient_outcomes` and pushes only a heartbeat". The rest of
ADR-0021 stands.

## Context

ADR-0021 measures the production version only once it has 500 predictions with known outcomes and
25 defaults. Below that, the job pushed only `bankml_performance_last_run_timestamp_seconds`.

A promotion therefore left the performance view blank for about ten days. Neither Grafana nor the
Nexus card could say which version was serving, what it scored on test, or how far it was from the
minimum sample. On 2026-11-16, the day credit-champion v3 was promoted, the only signal was that
the job had run.

## Decision

1. **Every scheduled run replaces the job's Pushgateway group** (`push_to_gateway`, not
   `pushadd_to_gateway`).
2. **It always pushes what is known without outcomes:**
   - the production version's `test_roc_auc` and `test_pr_auc`;
   - `n_labeled` and `n_positive`, the progress towards the minimum sample;
   - `bankml_performance_measured`, 1 when the run measured and 0 when it did not;
   - the run timestamp.
3. **It pushes the live metrics only when it measured.** These are ROC-AUC, PR-AUC, the drop
   against test, recall, alert rate and default rate.
4. **Every gauge except the timestamp carries `model_version`.** Replacing the group at a
   promotion drops the old version's live metrics instead of leaving them beside the new version.
5. **MLflow gets a run only when the job measured.** An `insufficient_outcomes` run logs nothing
   there, as before.

## Alternatives considered

**Keep the heartbeat only, and read the version and test metrics from MLflow in the dashboard.**
- It lost because Grafana has no MLflow datasource. The Nexus card would need a second client
  just for the registry.
- The job already resolves the production version and its test metrics on every run, so pushing
  them costs nothing.

**Merge into the group (`pushadd_to_gateway`) and keep the last live metrics.**
- It lost because after a promotion the previous version's live ROC-AUC would stay in the group
  for ten days. A dashboard showing it next to the new version's test ROC-AUC compares two
  different models.
- The alert rule would keep evaluating a model that no longer serves.

**Lower the minimum sample so measurement starts sooner.**
- It lost because the minimum exists to keep sampling noise out of the alert (ADR-0021). The
  waiting period is real, and should be shown rather than shortened.

## Consequences

- **The dashboard and the Nexus card show the waiting state.** Both show the serving version, its
  test ROC-AUC and "N of 500" from the first run after a promotion.
- **The live metrics disappear at each promotion.** Their history stays in Prometheus under the
  old `model_version` label.
- **The degradation alert keeps `noDataState: OK`.** `roc_auc_drop` still exists only after a
  measurement.
- **The staleness alert is unchanged.** It reads the timestamp, which every run pushes.
