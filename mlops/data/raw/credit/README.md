# Raw Home Credit data

Everything else in this directory is downloaded from Kaggle by hand (see
`docs/datasets/README.md`) and is never committed to git — only this README is.

## Tracked by DVC (see `configs/credit.yaml`'s `raw_data.tables`)

- `application_train.csv`
- `bureau.csv`
- `bureau_balance.csv`
- `previous_application.csv`
- `POS_CASH_balance.csv`
- `installments_payments.csv`
- `credit_card_balance.csv`

## Present but not used

Part of the same Kaggle zip, kept here for convenience, deliberately never `dvc add`-ed:

- `application_test.csv` — Kaggle's unlabeled leaderboard test set (no `TARGET` column).
  Only relevant for submitting to the competition, which this project does not do.
- `sample_submission.csv` — a submission-format template, not data.
- `HomeCredit_columns_description.csv` — a data dictionary (column meanings across all
  tables). Useful as a reference while writing the Pandera schemas, not itself a training
  table.
