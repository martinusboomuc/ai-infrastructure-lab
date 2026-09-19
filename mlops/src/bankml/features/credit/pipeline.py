"""Credit Risk feature pipeline entrypoint.

Wires together ADR-0008's synthetic anchor, the as-of aggregation functions, and core's
chronological-split/label-maturity mechanism (splitting.py) into the one feature table Phase 3
trains against. Run via `make features DOMAIN=credit` (mlops/dvc.yaml wraps this module).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yaml

from bankml.features.credit.aggregates import (
    bureau_aggregates,
    credit_card_balance_aggregates,
    installments_payments_aggregates,
    pos_cash_balance_aggregates,
    previous_application_aggregates,
)
from bankml.features.credit.anchor import compute_application_dates
from bankml.splitting import apply_label_maturity, chronological_split

CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "credit.yaml"

# Static applicant attributes, intrinsic to the application itself — no as-of/leakage concern,
# unlike the relational-table aggregates. CODE_GENDER is deliberately included here (for slice
# metrics) but excluded from model inputs in bankml.training.pipeline — see ADR discussion:
# a protected attribute as a training feature is a fair-lending problem, not a style choice.
BASE_APPLICANT_COLUMNS = [
    "CODE_GENDER",
    "DAYS_BIRTH",
    "DAYS_EMPLOYED",
    "AMT_INCOME_TOTAL",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "NAME_EDUCATION_TYPE",
    "NAME_FAMILY_STATUS",
    "NAME_HOUSING_TYPE",
    "CNT_CHILDREN",
    "EXT_SOURCE_1",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
]

DAYS_EMPLOYED_SENTINEL = 365243  # "not employed" — see configs/credit.yaml's sentinel_values


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_raw_tables(config: dict) -> dict[str, pd.DataFrame]:
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    raw_dir = data_root / config["raw_data"]["directory"]
    tables = {}
    for filename in config["raw_data"]["tables"]:
        key = filename.removesuffix(".csv")
        tables[key] = pd.read_csv(raw_dir / filename)
    return tables


def assemble_features(
    raw_tables: dict[str, pd.DataFrame], application_dates: pd.Series
) -> pd.DataFrame:
    """Build the base-applicant-columns-plus-relational-aggregates feature table for whichever
    applicants appear in `application_dates` (indexed by SK_ID_CURR), as-of each one's own
    mapped timestamp.

    The one function both the batch training path (`build_features`, below, using the synthetic
    per-applicant anchor from ADR-0008) and single-request serving
    (`bankml.serving.app`, using the actual request time as the decision timestamp) call — this
    is the concrete mechanism behind ADR-0006's "training and serving import the same module"
    and ADR-0009's request-time construction. `raw_tables["application_train"]` need not contain
    every applicant in `application_dates`'s index in the training-set sense; it only needs a
    row for each SK_ID_CURR being scored. TARGET is intentionally not included here — it is a
    training-only column, added by `build_features`, never available at serving time.
    """
    application_df = raw_tables["application_train"]
    base = application_df[["SK_ID_CURR", *BASE_APPLICANT_COLUMNS]].copy()
    base["APPLICATION_DATE"] = base["SK_ID_CURR"].map(application_dates)

    is_sentinel = base["DAYS_EMPLOYED"] == DAYS_EMPLOYED_SENTINEL
    base["DAYS_EMPLOYED_IS_SENTINEL"] = is_sentinel
    base["DAYS_EMPLOYED"] = base["DAYS_EMPLOYED"].astype(float)
    base.loc[is_sentinel, "DAYS_EMPLOYED"] = float("nan")

    aggregates = [
        bureau_aggregates(raw_tables["bureau"], raw_tables["bureau_balance"], application_dates),
        previous_application_aggregates(raw_tables["previous_application"], application_dates),
        pos_cash_balance_aggregates(raw_tables["POS_CASH_balance"], application_dates),
        installments_payments_aggregates(raw_tables["installments_payments"], application_dates),
        credit_card_balance_aggregates(raw_tables["credit_card_balance"], application_dates),
    ]

    features = base.set_index("SK_ID_CURR")
    for agg in aggregates:
        features = features.join(agg, how="left")
    features = features.reset_index()

    # An application entirely absent from an aux table (zero prior records) is a real, common
    # case, not missing data: its count/sum is genuinely 0. A *_MEAN column for the same
    # application stays NaN — "no data to average" is not the same claim as "average is zero".
    count_cols = [c for c in features.columns if c.endswith("_COUNT")]
    sum_cols = [c for c in features.columns if c.endswith("_SUM")]
    mean_cols = [c for c in features.columns if c.endswith("_MEAN")]
    features[count_cols] = features[count_cols].fillna(0).astype(int)
    features[sum_cols] = features[sum_cols].fillna(0.0).astype(float)
    # float64, not just left to fillna/pandas inference: an aggregate joined against a *table
    # with zero rows* (an applicant with no history in it at all — routine for a single-request
    # serving call, never seen in batch training) comes back `object`-dtyped straight out of the
    # groupby, not float64 — pandas can't infer a numeric type from an empty aggregation. Left
    # unfixed, a downstream model rejects the column outright ("pandas dtypes must be int, float
    # or bool"). Found by actually serving a request with an empty relational table, not by
    # inspection — see ADR-0009 and `tests/parity/test_training_serving_parity.py`.
    features[mean_cols] = features[mean_cols].astype(float)

    return features.sort_values("SK_ID_CURR").reset_index(drop=True)


def build_features(raw_tables: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    application_df = raw_tables["application_train"]
    anchor = config["synthetic_anchor"]
    application_dates = compute_application_dates(application_df, anchor["start"], anchor["end"])

    features = assemble_features(raw_tables, application_dates)
    features = features.merge(application_df[["SK_ID_CURR", "TARGET"]], on="SK_ID_CURR")

    features["SPLIT"] = chronological_split(features, "APPLICATION_DATE", config["split"])
    as_of = pd.Timestamp(config["label"]["as_of"])
    features["IS_MATURE"] = apply_label_maturity(
        features, "APPLICATION_DATE", config["label"]["maturity_days"], as_of
    )

    return features.sort_values("SK_ID_CURR").reset_index(drop=True)


def main() -> None:
    config = load_config()
    raw_tables = load_raw_tables(config)
    features = build_features(raw_tables, config)

    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    out_dir = data_root / "processed" / "credit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "features.parquet"
    features.to_parquet(out_path, index=False)
    print(f"Wrote {len(features)} rows, {len(features.columns)} columns, to {out_path}")


if __name__ == "__main__":
    main()
