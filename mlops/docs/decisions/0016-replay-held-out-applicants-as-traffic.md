# ADR-0016: Replay held-out applicants through the deployed API as monitoring traffic

**Status:** Accepted
**Date:** 2026-11-15

## Context

ADR-0015 scheduled the drift check, but the API has served 2 predictions since it went live. The
drift job needs at least 500 before PSI means anything (`DEFAULT_MIN_CURRENT`), so every daily
run reports `no_data`. The monitoring path, from prediction log to PSI to Prometheus, Grafana and
Discord, therefore has never run on served traffic. The same applies to the delayed-label
performance job, which joins logged predictions to their eventual outcomes.

There is no real user population to wait for. Any traffic the API sees has to be produced on
purpose.

A request is not a feature row. The API takes an applicant's raw fields plus their own
historical rows from six tables, and assembles features itself (ADR-0009). A request can only be
built from the raw Home Credit files, which live on `docker-01` (ADR-0014) and may not be
redistributed.

## Decision

1. **Replay real applicants from the test split.**
   - The sample is 5,000 applicants, evenly spaced through the test window in date order. They
     are spaced, not sampled at random, so the replay moves forward through time the way real
     traffic would, and the same config always selects the same applicants.
   - Each request carries the applicant's synthetic application date as `decision_date`
     (ADR-0008). The API's as-of aggregation therefore sees exactly the window training saw for
     the same applicant. `tests/parity/test_replay_requests.py` checks this: features assembled
     from each payload equal the batch features.
   - The test split is data the production model was not fit or tuned on, and it is later than
     the training window. Drift measured on it is real temporal drift, not noise from a
     synthetic generator.
2. **Build the requests once on `docker-01`, store them in Azure Blob, never in Git.**
   - `python -m bankml.features.credit.replay` reads the history tables in chunks, filtered by
     applicant. The full files do not fit in that VM's memory.
   - It writes gzipped JSON lines, about 11 MB for 5,000 requests, to the private `replay`
     container. That is the storage account that already holds the DVC remote and the prediction
     log.
3. **Send a daily batch from a k3s CronJob.**
   - `replay-credit` runs at 05:00 Lisbon time, an hour before the drift check, and posts 200
     requests (`bankml.monitoring.replay`).
   - A cursor blob records how far the replay has got. A missed or repeated run neither skips
     nor resends applicants, and the cursor wraps to the start at the end of the file.
   - A run fails when more than 10% of its requests fail.
4. **Mark replayed traffic in the prediction log.**
   - The sender sets `X-Traffic-Source: replay`. The API writes it into every log record as
     `traffic_source`, `live` by default, and refuses any other value.
   - The drift job reads both kinds today. The field exists so that any later analysis can
     separate them, and so the log never presents replayed traffic as real.

## Alternatives considered

**Generate synthetic applicants from fitted distributions.**
- No raw data would be involved, so nothing restricted leaves `docker-01`.
- It lost because a generator only reproduces what it was told to produce. Drift would then
  measure the generator, not the world.
- A synthetic applicant also has no relational history, so the request path ADR-0009 built would
  go unexercised.

**Send the requests from `docker-01`, reading the raw files directly each day.**
- No intermediate file would be needed.
- It lost because it schedules work on a pet VM again (the reason ADR-0015 moved drift to k3s).
- Rebuilding payloads daily from 2.5 GB of CSV is also most of a day's memory headroom on that
  host, spent to produce the same requests.

**Replay the whole test split at once.**
- Drift would be measurable after a single run.
- It lost because tens of thousands of requests in one burst say nothing about how a real API
  behaves, and they would scale the Container App out for no reason.
- A daily batch of 200 crosses the 500-record threshold on the third day.

**Commit a small request file to the repository.**
- This would be the simplest storage.
- It lost on the hard rule: the payloads are raw Home Credit rows, and raw data never enters Git.

## Consequences

- **Drift is measured on traffic.** From the third daily run, the drift check computes PSI on
  logged predictions instead of reporting `no_data`. The delayed-label performance job has
  outcomes to join, because every replayed `applicant_id` is a real applicant with a known label.
- **The production log is mostly replayed traffic.** It is marked, and a reader who skips the
  `traffic_source` field will still mistake it for real usage.
- **The drift window is all time.** The drift job reads every logged record, not the most recent
  window. Once replay has run for a while, a sudden shift is diluted by everything logged before
  it. A rolling window is a separate change.
- **The API is public and unauthenticated.** Anyone who finds the URL can add records to the
  log. That was already true; replay only makes it more visible.
- **The file needs rebuilding when the model changes.** The requests are tied to the raw tables,
  not to a model version. A new production model trained on a different split needs a new file,
  and uploading one resets the cursor.
