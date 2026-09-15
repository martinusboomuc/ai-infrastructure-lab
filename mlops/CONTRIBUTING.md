# Contributing

This is a personal engineering project, but it is developed under the conventions of a
maintained repository — because the conventions are part of what is being practised.

---

## Development setup

```bash
make setup     # uv sync + pre-commit install
make lint      # ruff check + format check
make test      # pytest
```

Python 3.12. Dependencies are managed with `uv`; `uv.lock` is committed and CI installs from it.

---

## Branching and commits

Work happens on branches off `main`. `main` is always in a state where `make lint && make test`
passes.

Branch names are short and descriptive: `as-of-bureau-aggregation`, `serving-request-ids`,
`defer-feature-store-adr`.

Commit subjects are written as a plain imperative sentence — what the commit does, in normal
English. No type prefixes, no scopes, no tags.

```
Add as-of aggregation for bureau balance
Propagate request id into the prediction log
Record the decision to defer the feature store
Fix sentinel handling in DAYS_EMPLOYED
```

Keep the subject under ~70 characters. If the change needs justification, put it in the body
after a blank line — the body is where the reasoning belongs, not in a machine-readable prefix.

---

## Pull requests

Even solo. The PR is where the reasoning is recorded, and the diff is reviewable later.

A PR should state what changed, why, and how it was verified. CI must be green before merge.

---

## Definition of done

A change is done when:

- [ ] Tests cover the new behaviour, including the failure case
- [ ] `make lint && make test` passes locally and in CI
- [ ] Anything touching feature construction passes the **leakage test**
- [ ] Config changes are reflected in the relevant domain config, not hardcoded
- [ ] Documentation affected by the change is updated in the same PR
- [ ] A decision with a real alternative is recorded as an ADR

Documentation drifting behind code is treated as a bug, not as debt.

---

## Architecture decisions

Any choice with a defensible alternative gets an ADR in
[`docs/decisions/`](docs/decisions/README.md). Use the template there, number sequentially, and
never edit a decision after it is accepted — supersede it with a new one that links back.

---

## Testing conventions

| Kind | Location | Runs |
|---|---|---|
| Unit | `tests/unit/` | Every PR |
| Contract (Pandera schemas) | `tests/contracts/` | Every PR |
| Leakage | `tests/leakage/` | Every PR touching features |
| Pipeline smoke (Churn, Marketing fixtures) | `tests/pipeline/` | Every PR |
| Full training run | — | Manually, not in CI |

The Tier 2 datasets exist so the full pipeline can run in CI in seconds. Keep them fast; if a
smoke test starts taking minutes, it has stopped being a smoke test.

---

## Data

Raw data is never committed. It is tracked by DVC against a private remote, because some source
datasets carry competition terms that restrict redistribution. If a change requires new data,
add the DVC pointer and document the source and its terms in
[`docs/datasets/`](docs/datasets/README.md).
