# ADR-0003: Pandera for data validation

**Status:** Accepted
**Date:** 2026-09-15

## Context

Every pipeline stage must validate its input against a contract before doing work. Home Credit
alone has seven tables with distinct schemas, and the serving path must enforce the *same*
contract the training path used — otherwise validation is theatre.

Great Expectations is the better-known name and carries recruiter recognition. Pandera is the
lighter, code-first alternative.

## Decision

Use **Pandera**. Schemas are declared as Python classes in `src/bankml/validation/`, imported by
both the training pipeline and the FastAPI service, and exercised directly by `pytest`.

## Alternatives considered

**Great Expectations.** More capable: data docs, a rich expectation catalogue, profiling, and
broader name recognition. Rejected on cost-to-value. It brings a context/datasource/checkpoint
configuration layer that is substantial to set up and maintain, its API has changed
significantly across major versions (which dates tutorials and invites breakage), and its
generated documentation is a weaker artifact than a passing test suite. For contracts over
pandas DataFrames, the incremental validation capability over Pandera is small and the
incremental setup is large.

**Hand-rolled assertions.** Rejected: no schema coercion, no composability, no reusable contract
object to share between training and serving, and it degrades into scattered `assert` statements.

**Pydantic alone.** Correct for the API request payload and used there, but it validates records,
not DataFrames. It cannot express column-level statistical checks or cross-column constraints
over a table. Pandera covers the DataFrame layer; Pydantic covers the request layer.

## Consequences

- Contracts are ordinary Python, so they are diffable, testable and reviewable in a PR.
- One contract object is genuinely shared between training and serving, which is what prevents
  skew at the validation boundary.
- No data-docs site is generated. The data catalogue in Phase 7 will be generated from the
  Pandera schemas instead, which keeps a single source of truth.
- Great Expectations does not appear on the stack list. If that recognition turns out to matter,
  it can be added later as a reporting layer over the same data without displacing Pandera.
