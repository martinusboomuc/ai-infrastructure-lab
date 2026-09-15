# Working conventions for this project

BankML Platform — a production-inspired MLOps platform for banking ML. Read `README.md` for
scope and `ARCHITECTURE.md` for how it fits together. Decisions with a real alternative live in
`docs/decisions/` as ADRs; read the relevant one before changing anything it covers.

---

## Hard rules

These are not style preferences. Breaking one invalidates the project's central claims.

**Never use a random train/test split.** All splits are chronological, read from the domain
config, with an explicit gap window between train and validation. `train_test_split(shuffle=True)`,
`KFold`, `StratifiedKFold` and friends are banned in `src/`. See
`docs/decisions/0004-temporal-validation.md`.

**Never build a feature that can see past its own decision timestamp.** Every aggregation over
relational history takes an explicit as-of timestamp. The leakage test in `tests/leakage/` is the
enforcement mechanism — if a change makes it fail, the change is wrong, not the test. Never skip,
weaken or `xfail` it to get something merged.

**Never commit raw data.** No CSV, Parquet, archive or model binary enters Git. Data is tracked by
DVC against a private remote, because several source datasets carry competition terms restricting
redistribution.

**Never hardcode a data path.** The data root comes from the `BANKML_DATA_ROOT` environment
variable (see `.env.example`). It currently points at a local folder and will later point at a
homelab machine. An absolute path like `/Users/...` or `/Volumes/...` appearing anywhere in `src/`
is a bug — it breaks CI and every other machine.

**Never drop a metric to make a model look better.** Evaluation reports PR-AUC, recall at a fixed
FPR, alert volume against budget, and expected cost. ROC-AUC alone is never a promotion gate.

---

## Git

**Never run a Git command.** Not `add`, `commit`, `push`, `pull`, `fetch`, `merge`, `rebase`,
`checkout`, `branch`, `stash`, `reset`, or `status` — and no `gh` commands either. This includes
read-only commands.

I run every Git operation myself, by hand, in my own terminal. This is deliberate: I want to see
and approve every change to the history, and agent-run Git has left stale lock files in
`.git/` before.

When work is ready to be committed, stop and tell me, and propose a commit message in the style
below. Do not offer to run it. If you need to know what changed, read the files directly rather
than reaching for `git diff`.

---

## Commit and PR conventions

Commit subjects are a plain imperative sentence in normal English. **No type prefixes, no scopes,
no colons, no tags.**

```
Add as-of aggregation for bureau balance
Propagate request id into the prediction log
Fix sentinel handling in DAYS_EMPLOYED
```

Not `feat(features): ...`, not `docs: ...`, not `[MLOPS] ...`.

Subject under ~70 characters. Reasoning goes in the body after a blank line, not in a
machine-readable prefix.

**Do not add `Co-Authored-By` trailers, `Generated with` lines, tool URLs, or any other
attribution footer to commits or PR descriptions.** Leave the commit message as written.

Branch names are short and descriptive, no prefixes: `as-of-bureau-aggregation`,
`serving-request-ids`.

Commit in small, coherent increments — one logical change per commit. Do not batch unrelated work
into a single large commit.

---

## Commands

```bash
make setup     # uv sync + pre-commit install
make lint      # ruff check + format check
make test      # pytest
make data      # verify data root is mounted, then dvc pull
```

Python 3.12, `uv` for dependencies (`uv.lock` is committed). Never invoke `pip install` directly —
use `uv add`.

---

## Structure

Domain-specific logic lives in exactly two places: `configs/<domain>.yaml` and
`src/bankml/features/<domain>/`. Everything else in `src/bankml/` is domain-agnostic.

When adding a domain, do not modify core modules. If the core seems to need a change, that is a
design problem worth surfacing — say so rather than working around it. See
`docs/decisions/0002-vertical-slice-first.md`.

---

## Modelling

| Domain | Champion | Challenger |
|---|---|---|
| Credit Risk | WoE + logistic scorecard (`optbinning`) | LightGBM |
| Fraud | LightGBM | Logistic regression |
| Churn, Marketing | Logistic regression (CI fixtures only) | — |

Credit Risk is scorecard-first for explainability reasons, not by accident. Read
`docs/decisions/0005-scorecard-champion-gbm-challenger.md` before changing it.

---

## When you make a decision

If you choose between real alternatives — a library, an architecture, a modelling approach — write
an ADR in `docs/decisions/` using the template in that folder's README. Do not edit an accepted
ADR; supersede it with a new one that links back.

---

## Tone

Tell me when something in this file is wrong, or when a requested change conflicts with an ADR.
Do not silently work around a constraint to make a task succeed.
