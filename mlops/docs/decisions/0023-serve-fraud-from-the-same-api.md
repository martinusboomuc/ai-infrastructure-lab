# ADR-0023: Serve Fraud from the same API, with a 30-day card history in each request

**Status:** Accepted
**Date:** 2026-11-17

## Context

Credit Risk is the only served model. Fraud was trained in Phase 6 to prove the platform is
domain-agnostic, and was never registered or served.

Serving it raised three questions.

- **Where it runs.** The API's resident memory is 437 MB with one model, and nearly all of it is
  libraries: pandas, LightGBM, SHAP, optbinning, MLflow. A scorecard is a few megabytes.
- **What a request carries.** ADR-0009 has a request carry the history its features need,
  because there is no online store (ADR-0006). Three Fraud features used the card's entire
  history: its average amount, its usual merchant location and the time since its last
  transaction. In the test split, a transaction has 2,230 earlier transactions on the same card
  on average, up to 4,391. A replay file of 30,000 such requests would hold about 67 million
  history rows.
- **How much replay traffic.** Fraud is 0.38% of test-split transactions. The performance job
  (ADR-0021) needs 25 positives in its 30-day window. At Credit Risk's 200 requests a day, a
  window holds about 23 frauds and is never measured.

## Decision

1. **One API process serves both domains.**
   - `/predict/fraud` sits beside `/predict/credit`.
   - Each domain loads `<domain>-champion@production` at startup.
   - Credit Risk is required: without it the API does not start, as before.
   - A domain with no production version yet answers 503 and does not stop the API.
   - `/health` lists every loaded version. It keeps `model_version` as Credit Risk's, for the
     callers that already read it.
2. **Fraud's history features look back 30 days at most** (`velocity.HISTORY_DAYS`).
   - `CC_AMT_AVG_PRIOR` becomes `CC_AMT_AVG_30D`.
   - The usual merchant location is the 30-day mean.
   - The time since the last transaction is missing when that transaction is older than 30
     days, exactly as serving would see it.
   - Three features compare the transaction with the card's own last 30 days:
     `AMT_ZSCORE_30D`, `CC_CATEGORY_TXN_COUNT_30D` and `AMT_DEVIATION_FROM_CC_CATEGORY_AVG`.
     A large travel purchase is ordinary for a card that travels and not for one that never
     has. They were added after the first windowed model ranked poorly within some categories
     (travel 0.747 against 0.946 overall); see ADR-0024.
   - The leakage test recomputes every history feature independently, and checks the boundary
     with a transaction 44 days after the previous one.
3. **A Fraud request carries the transaction and the card's last 30 days.**
   - Each history row has five fields: time, category, amount, merchant latitude and merchant
     longitude.
   - The API rejects history at or after the transaction's time, and timestamps with a zone.
     Sparkov records local time without one, and the model was trained on it.
   - The request contract (`validation/fraud/request.py`) has none of the cardholder's name,
     address, job or date of birth, which Sparkov carries and the model never reads.
4. **Fraud replays 1,000 transactions a day.**
   - 30,000 test-split transactions, evenly spaced in time, are one 30-day window without reuse,
     with about 115 frauds in it.
   - The sender streams the request file instead of decompressing it whole. Compressed it is
     80 MB; decompressed it is 518 MB. A batch of 1,000 takes 137 MB of memory to read.

## Alternatives considered

**A separate Container App for Fraud.**
- It isolates the domains: a Fraud deploy or crash cannot touch Credit Risk.
- It lost because it doubles the fixed cost, a second copy of the same 400 MB of libraries, for
  a model of a few megabytes. That isolation matters at a traffic level this project does not
  have.
- If one domain's traffic or release cadence ever diverges, splitting them is a deployment
  change, not a code change: the endpoints are already separate.

**Keep the full-history features and send the whole history.**
- It lost because each request would carry about 2,200 rows, and the replay file would be
  about 18 times larger.
- A real fraud system does not score against a card's whole life either. Windowed aggregates
  are the norm.

**Send precomputed aggregates instead of transactions.**
- It lost because the aggregates would be computed outside the training code, which is exactly
  the training/serving skew ADR-0009 avoids. It is also the online store ADR-0006 defers.

**Oversample fraud in the replay.**
- It lost because the alert rate and precision would describe a fraud rate that does not exist.
  ROC-AUC would survive it, and nothing else would.

## Consequences

- **The Fraud model must be retrained** on the windowed features before it is registered. The
  Phase 6 metrics described the full-history features and no longer apply. On a dry run, test
  PR-AUC is 0.708, ROC-AUC 0.964, and recall at a 1% alert rate 0.936.
- **Request and replay parity is tested on the API's own path.** On the real data, 50 of 50
  sampled replay requests rebuilt the batch features exactly. Building one request's features
  takes 22 ms at the median and 41 ms at most. A whole prediction, with SHAP reason codes from
  the LightGBM, takes about 120 ms.
- **A Fraud request is about 17 KB**, against a few KB for Credit Risk.
- **The replay file takes about 40 s and 1 GB of memory to build** on the full data.
- **Drift and performance for Fraud come next.** The prediction log already partitions by
  domain. The performance job reads `applicant_id`, which Fraud records as `transaction_id`, so
  it needs the entity key from the domain config.
- **A bad Fraud model can still fail the shared process at load time.** A missing one cannot,
  and Credit Risk loads first.
