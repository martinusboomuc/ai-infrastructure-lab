# ADR-0007: Synthetic fixtures for the CI leakage test

**Status:** Accepted
**Date:** 2026-09-18

## Context

ADR-0004 requires a leakage test in CI: features built against the full relational tables and
against the tables truncated at a row's decision timestamp must be identical. That test needs
data to run against, and the real Home Credit tables are a ~2.5 GB, seven-table Kaggle
competition dataset whose licensing forbids redistribution — `docs/datasets/README.md` states
this outright, and no raw data is committed to this repository under any circumstance.

CI runs on every pull request touching `mlops/**`, on ephemeral GitHub-hosted runners, from a
clean clone. Whatever the leakage test runs against has to be available in that environment
without violating the licensing restriction and without materially slowing every PR.

## Decision

The leakage test runs against small **synthetic** fixture tables, not real Home Credit data.
Fixtures live in git at `tests/fixtures/credit/` — a handful of fabricated rows per table, using
the same column names, dtypes, and the same relative-day-offset timestamp convention as the real
tables (including a `DAYS_EMPLOYED` sentinel row), but no values drawn from or derived from the
actual dataset.

The test exercises the real feature-pipeline code in `src/bankml/features/credit/` against these
fixtures, so it proves the leakage-prevention *mechanism* works, not that a specific real dataset
happens to be leak-free.

## Alternatives considered

**A real-data subset committed to git.** Rejected outright: the dataset's licensing restricts
redistribution of the data, not just bulk redistribution — a ten-row excerpt is still Kaggle
competition data, and `docs/datasets/README.md`'s "no raw data is committed to this repository"
rule doesn't carve out an exception for small slices.

**A full `dvc pull` from the private Azure Blob remote in every CI run.** Would require Azure
credentials as GitHub secrets, couples every PR's CI time to an external network dependency and
the remote's availability, and contradicts the "`make lint && make test` passes from a clean
clone" standard Phase 0 already established. Also makes the leakage test slower exactly where
speed matters most — it runs on every feature-touching PR.

## Consequences

- The leakage test is fully self-contained: no data download, no credentials, no dependency on
  the user having run Stage 3 (downloading the real dataset) at all. It runs from a clean clone.
- It proves the mechanism, not the data. A real full-dataset leakage check remains a manual,
  not-in-CI verification, consistent with `CONTRIBUTING.md`'s testing table ("full training run
  — manually, not in CI").
- The fixtures need to be kept honest as the real schema is inspected in Stage 3 — if a real
  column turns out to have a property the fixture doesn't exercise (a new sentinel value, a
  different join cardinality), the fixture is updated to match, the same way any test fixture
  drifts and gets corrected.
