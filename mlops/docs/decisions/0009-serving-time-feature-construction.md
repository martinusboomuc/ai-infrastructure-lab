# ADR-0009: Serving-time feature construction from request-supplied historical records

**Status:** Accepted
**Date:** 2026-09-18

## Context

[ADR-0006](0006-defer-feature-store.md) already decided there is no online feature store:
features are "recomputed at request time in serving rather than looked up," and training and
serving import the same feature module. It did not specify what a request actually carries to
make that recomputation possible.

Most of the Credit Risk feature set is not the applicant's own static attributes — it is
relational aggregates over `bureau`, `bureau_balance`, `previous_application`,
`POS_CASH_balance`, `installments_payments` and `credit_card_balance`
(`src/bankml/features/credit/aggregates.py`), each built as-of the applicant's own decision
timestamp (`anchor.py`, enforced by the CI leakage test). Two real options exist for a single
serving request:

**A. Request-supplied historical records.** The request carries the applicant's static fields
plus this one applicant's own historical rows, shaped like the raw CSVs. Serving calls the exact
same aggregate functions training uses, with `application_dates` set to `{applicant_id:
request_time}` instead of the synthetic per-applicant anchor ([ADR-0008](0008-synthetic-application-date-anchor.md))
batch training uses.

**B. Static-fields-only simplification.** Serving scores only the applicant's own attributes,
treating the relational aggregates as unavailable at request time (all-NaN / all-zero, as if the
applicant had no history).

Option B is simpler to call, but it doesn't exercise the aggregate functions at all — a
training-vs-serving parity test built on it would only prove the six columns in
`BASE_APPLICANT_COLUMNS` match, which is not where the platform's central technical claim
(point-in-time-correct feature construction) actually lives. It would also mean every request
scores as if the applicant had zero credit history, which is a materially different (and wrong)
input to the model, not a faithful stand-in for "we don't have an online store."

## Decision

Serving requests carry the applicant's static attributes plus, per relational table, that one
applicant's own historical rows (empty arrays are a legitimate "no history" case, handled the
same way the batch pipeline already handles it — see `assemble_features`'s count/sum-column
fillna). The decision timestamp is the actual request time (with an optional override for
deterministic testing), not the synthetic anchor, which is meaningless outside the training set
it was built over. `src/bankml/features/credit/pipeline.py::build_features` is split so its
base-columns-plus-aggregates core (`assemble_features`) takes `application_dates` as a plain
argument — training supplies the synthetic anchor, serving supplies the single-row request-time
mapping. Both call sites run identical code from that point on.

Each historical table validates against its own existing Pandera schema in
`src/bankml/validation/credit/` (already used at the raw-ingestion boundary) before being passed
in; the applicant's own fields validate against a new, narrower `ApplicationRequestSchema`
(`validation/credit/request.py`) covering only the columns the model actually consumes.

## Alternatives considered

**B (static-fields-only), rejected above.**

**A hand-rolled request-time cache of recent history, keyed by applicant ID.** Rejected for the
same reason ADR-0006 rejected a hand-rolled online feature cache: operational burden without
standard tooling, and it reintroduces exactly the stateful service ADR-0006 deferred.

## Consequences

- The serving request payload is larger and more structured than a typical "just the form
  fields" scoring API — this is the direct, honest cost of not having an online store, stated
  rather than hidden behind a simplified demo payload.
- The training-vs-serving parity test (`tests/parity/test_training_serving_parity.py`) is a real
  test: it feeds a real training-set applicant's actual historical rows and real
  `APPLICATION_DATE` through the serving path and asserts identical features to the batch path.
- This decision is what actually exposed two real, pre-existing bugs, neither caught by the
  parity test itself (which only checks `assemble_features`'s output, not a model scoring it):
  an aggregate `*_MEAN`/`*_SUM` column comes back `object`-dtyped, not `float64`, when its
  source relational table has zero rows for an applicant — invisible in batch training, where
  some row always has real history, but routine for a single new applicant with no history in a
  given table. And a categorical column's levels (and, transitively, how many columns even
  count as categorical) must be fixed once from training data, not re-inferred per call, or a
  tree model's booster rejects a single-row request outright. Both are fixed in
  `features/credit/pipeline.py::assemble_features` and `features/credit/prepare.py`, not worked
  around in serving — neither would have surfaced without actually serving a request with a
  genuinely empty history table, which only this design (as opposed to Option B) does.
- If a genuinely low-latency serving requirement ever appears, the trigger to revisit is the same
  one ADR-0006 already names: precomputed aggregates behind a real online store, at which point
  the request payload will shrink back down to just an applicant identifier.
