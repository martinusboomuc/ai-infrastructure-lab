# Configs

One YAML file per domain: `credit.yaml`, `fraud.yaml`, `churn.yaml`, `marketing.yaml`. Each file
is the single place domain-specific settings live outside `src/bankml/features/<domain>/` — see
`docs/decisions/0002-vertical-slice-first.md`.

No domain config exists yet. The first one, `credit.yaml`, is drafted in Phase 2 alongside the
Credit Risk feature pipeline.
