# ADR-0008: Synthetic calendar anchor for Home Credit's relative timestamps

**Status:** Accepted
**Date:** 2026-09-18

## Context

Home Credit's raw data carries no real calendar date anywhere. Every `DAYS_*` and
`MONTHS_BALANCE` column across all 7 tables — confirmed directly against
`HomeCredit_columns_description.csv`, not from memory — is documented as relative to a single
anchor: "current application." `bureau.DAYS_CREDIT` is "how many days before current application
did client apply for Credit Bureau credit"; `previous_application.DAYS_DECISION` is "relative to
current application when was the decision about previous application made"; `bureau_balance` and
`POS_CASH_balance`'s `MONTHS_BALANCE` are "month of balance relative to application date." None of
these are relative to each other's own event — they all share the same per-`SK_ID_CURR` anchor,
which itself has no real value anywhere in the data.

ADR-0004 requires chronological splits, a gap window, and a label maturity window — all of which
need a genuine per-row timestamp to operate on. `ARCHITECTURE.md`'s "Temporal correctness"
section, written in Phase 1 before any real data existed, already commits to the *shape* this
should take: calendar `from`/`to` split windows with an explicit `gap_days`, and a
`label.maturity_days` field, with a worked example (`train 2016-01-01→2017-06-30`,
`gap_days: 30`, `validation 2017-08-01→2017-12-31`, `test 2018-01-01→2018-06-30`,
`label.maturity_days: 540`). That example presupposes calendar dates exist. They don't, unless
one is constructed.

## Decision

Assign each `SK_ID_CURR` a synthetic `APPLICATION_DATE`: sort applications by `SK_ID_CURR`
ascending and linearly map rank onto a fixed calendar window, **2016-01-01 through 2018-06-30** —
reused verbatim from `ARCHITECTURE.md`'s own example rather than inventing a new one, since no
value in that range is any more or less arbitrary than any other and reusing it keeps the
project's own documents consistent with each other.

Every other table's own effective timestamp is then that row's `SK_ID_CURR`'s `APPLICATION_DATE`
plus its own `DAYS_*` column (in days) or `MONTHS_BALANCE` column (in calendar months), matching
each column's documented "relative to current application" semantics exactly. `bureau_balance`
has no `SK_ID_CURR` of its own — it joins to one through `bureau.csv`'s `SK_ID_BUREAU`.

This derivation is Credit-Risk-specific, per ADR-0002's rule that domain logic lives only in
`configs/<domain>.yaml` and `src/bankml/features/<domain>/`. It is implemented there (Phase 2
Stage 5), never in core. Core's chronological-split and label-maturity mechanism operates on any
DataFrame with a real timestamp column, agnostic to how that timestamp was produced, so Fraud can
reuse it unmodified in Phase 6 — Fraud's data already carries real timestamps and will never need
this construction.

## Alternatives considered

**No calendar mapping — split purely by `SK_ID_CURR` rank or percentile.** Rejected:
`ARCHITECTURE.md`'s config format already expects calendar `from`/`to` dates, and a rank-based
split mechanism in core would be Credit-Risk-shaped rather than genuinely domain-agnostic,
undermining the reuse Phase 6's portability proof depends on.

**Purely random, uncorrelated synthetic dates per application.** Rejected: `SK_ID_CURR`-order as
a time proxy is the standard, publicly precedented assumption for this specific competition
dataset (ID assignment is widely understood to track submission order). Random dates would let
the leakage-test *mechanism* still function, but would strip any interpretive meaning from the
chronological-split metrics Phase 3 will report — a temporal AUC drop only means something if the
split roughly tracks real submission order.

## Consequences

- These are not real Home Credit application dates. This must stay visible everywhere the anchor
  is used — the ADR, `configs/credit.yaml`'s comments, and any model card or report that later
  cites dates from this pipeline — so nobody mistakes 2016-2018 for ground truth.
- The specific window is arbitrary by necessity (no ground truth exists to derive it from), but
  internally consistent: reused from `ARCHITECTURE.md` rather than re-invented.
- The assumption is confined to Credit Risk's feature module. If a future domain also lacks real
  timestamps, it gets its own ADR and its own domain-specific anchor construction, not a change to
  this one or to core.
