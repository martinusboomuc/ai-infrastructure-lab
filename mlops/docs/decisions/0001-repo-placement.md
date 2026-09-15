# ADR-0001: BankML lives inside `ai-infrastructure-lab/mlops`

**Status:** Accepted
**Date:** 2026-09-15

## Context

`ai-infrastructure-lab` is an existing homelab repository spanning infrastructure, containers,
automation, monitoring and MLOps. BankML Platform is substantially larger than a lab exercise: it
has its own lifecycle, its own CI, its own deployment, and is intended to be the portfolio's
flagship piece.

Placing it inside the lab makes it a subdirectory of a repository about something broader.
Splitting it out makes it a project in its own right, but fragments the portfolio.

## Decision

BankML Platform is developed at `ai-infrastructure-lab/mlops/`, with `mlops/` treated as the
project root: its own README, architecture, roadmap and ADRs.

## Alternatives considered

**A separate public repository, `bankml-platform`.** Strongest option on visibility: its own
CI badge, its own stars, its own README as the landing page, and a clean commit history focused
on one product. Rejected *for now* because splitting later is a cheap, mechanical operation
(`git subtree split` preserves history), while consolidating two repositories later is not. The
cost of deferring is close to zero; the cost of a premature split is a thinner-looking lab.

**A git submodule inside the lab.** Rejected: submodules impose real friction on contributors and
on CI for a benefit — independent versioning — that this project does not need.

## Consequences

- The project root is `mlops/`, not `bankml-platform/`. All paths in the documentation are
  relative to `mlops/`.
- CI workflows must be path-scoped so that changes elsewhere in the lab do not trigger BankML
  pipelines, and vice versa.
- GitHub surfaces the lab's top-level README, not BankML's. The lab README must therefore link
  prominently to `mlops/`.
- **Revisit trigger:** once Phase 4 is deployed and the project has a live endpoint and a real
  CI/CD pipeline, reassess splitting it into its own repository via `git subtree split`. Record
  that as a new ADR superseding this one.
