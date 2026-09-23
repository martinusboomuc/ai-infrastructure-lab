"""Fraud Detection feature pipeline entrypoint (Phase 6 — the portability proof).

Wires together the real Sparkov timestamps (no synthetic anchor needed, unlike Credit Risk's
ADR-0008), this domain's own as-of history features (velocity.py), and core's unmodified
chronological-split/label-maturity mechanism (splitting.py) into the one feature table training
runs against. Run via `make features DOMAIN=fraud`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yaml

from bankml.features.fraud.velocity import add_customer_history_features, haversine_km
from bankml.splitting import apply_label_maturity, chronological_split

CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "fraud.yaml"

# Columns carried from the raw transaction into the assembled feature table. amt and category are
# intrinsic to the transaction itself (no as-of/leakage concern — the transaction's own amount and
# merchant category are known at the moment it happens), analogous to Credit Risk's
# BASE_APPLICANT_COLUMNS. Everything else here is a derived velocity/geo-distance/recency feature.
BASE_TRANSACTION_COLUMNS = ["category", "amt"]


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_raw_tables(config: dict) -> dict[str, pd.DataFrame]:
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    raw_dir = data_root / config["raw_data"]["directory"]
    tables = {}
    for filename in config["raw_data"]["tables"]:
        key = filename.removesuffix(".csv")
        # index_col=0: the raw files carry an unnamed pandas-index column from however Sparkov's
        # generator wrote them out — not transaction data, and rejected outright by
        # TransactionSchema's strict=True if left in.
        tables[key] = pd.read_csv(raw_dir / filename, index_col=0)
    return tables


def assemble_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build the base-transaction-columns-plus-history-features table for every transaction in
    `raw_df`, as-of each transaction's own timestamp.

    `raw_df` need not be the full training set in the training-set sense; it only needs enough of
    a customer's (cc_num) transaction history to compute that customer's velocity/recency
    features correctly — same shape of contract as Credit Risk's assemble_features, just without
    a separate application_dates argument, since each row supplies its own decision timestamp
    directly (trans_date_trans_time), unlike credit's per-applicant synthetic anchor. TARGET is
    intentionally not included here — see build_features.
    """
    df = raw_df.copy()
    df["trans_date_trans_time"] = pd.to_datetime(df["trans_date_trans_time"])
    df = df.sort_values(["cc_num", "trans_date_trans_time"]).reset_index(drop=True)

    df["DISTANCE_FROM_HOME_KM"] = haversine_km(
        df["lat"], df["long"], df["merch_lat"], df["merch_long"]
    )
    df = add_customer_history_features(df)

    df["TRANSACTION_HOUR"] = df["trans_date_trans_time"].dt.hour
    df["TRANSACTION_DAYOFWEEK"] = df["trans_date_trans_time"].dt.dayofweek

    columns = [
        "trans_num",
        "trans_date_trans_time",
        *BASE_TRANSACTION_COLUMNS,
        "DISTANCE_FROM_HOME_KM",
        "DISTANCE_FROM_USUAL_MERCHANT_KM",
        "CC_TXN_COUNT_1H",
        "CC_TXN_COUNT_24H",
        "CC_AMT_SUM_24H",
        "CC_AMT_AVG_PRIOR",
        "AMT_DEVIATION_FROM_CC_AVG",
        "CC_SECONDS_SINCE_LAST_TXN",
        "TRANSACTION_HOUR",
        "TRANSACTION_DAYOFWEEK",
    ]
    return df[columns].sort_values("trans_date_trans_time").reset_index(drop=True)


def build_features(raw_tables: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    # Sparkov's own train/test file split is not used as given (docs/datasets/README.md,
    # configs/fraud.yaml) — the two files are concatenated back into one universe of transactions
    # and re-split chronologically below.
    combined = pd.concat(raw_tables.values(), ignore_index=True)
    features = assemble_features(combined)

    target = combined.set_index("trans_num")["is_fraud"].rename("TARGET")
    features = features.join(target, on="trans_num")

    features["SPLIT"] = chronological_split(features, "trans_date_trans_time", config["split"])
    as_of = pd.Timestamp(config["label"]["as_of"])
    features["IS_MATURE"] = apply_label_maturity(
        features, "trans_date_trans_time", config["label"]["maturity_days"], as_of
    )

    return features.sort_values("trans_date_trans_time").reset_index(drop=True)


def main() -> None:
    config = load_config()
    raw_tables = load_raw_tables(config)
    features = build_features(raw_tables, config)

    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    out_dir = data_root / "processed" / "fraud"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "features.parquet"
    features.to_parquet(out_path, index=False)
    print(f"Wrote {len(features)} rows, {len(features.columns)} columns, to {out_path}")


if __name__ == "__main__":
    main()
