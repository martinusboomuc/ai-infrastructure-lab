"""As-of, point-in-time-correct customer/card (cc_num) history features for Sparkov transactions.

Every feature here is computed using only transactions strictly before the transaction's own
timestamp, for the same cc_num — never itself, never a same-timestamp or later one.
tests/leakage/test_fraud_leakage.py is the enforcement mechanism (ADR-0007's pattern, adapted to
one flat table instead of Credit Risk's relational tables): a naive, unfiltered rolling window
would include the row's own transaction; this module's `closed="left"` rolling windows and
`shift(1)`-before-`expanding()` calls are exactly what keeps that from happening.

DISTANCE_FROM_HOME_KM is deliberately NOT computed here — it needs only the row's own lat/long
and merch_lat/merch_long, carries no leakage risk, and lives directly in
pipeline.py's assemble_features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(x) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def _rolling_counts_and_sums(group: pd.DataFrame) -> pd.DataFrame:
    indexed = group.set_index("trans_date_trans_time")
    return pd.DataFrame(
        {
            "CC_TXN_COUNT_1H": indexed["amt"].rolling("1h", closed="left").count().to_numpy(),
            "CC_TXN_COUNT_24H": indexed["amt"].rolling("24h", closed="left").count().to_numpy(),
            "CC_AMT_SUM_24H": indexed["amt"].rolling("24h", closed="left").sum().to_numpy(),
        },
        index=group.index,
    )


def _expanding_prior_means(group: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CC_AMT_AVG_PRIOR": group["amt"].shift(1).expanding().mean(),
            "CC_USUAL_MERCH_LAT": group["merch_lat"].shift(1).expanding().mean(),
            "CC_USUAL_MERCH_LONG": group["merch_long"].shift(1).expanding().mean(),
        },
        index=group.index,
    )


def add_customer_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must already be sorted by (cc_num, trans_date_trans_time) with `trans_date_trans_time`
    already parsed to a real datetime dtype — pipeline.py's assemble_features guarantees both
    before calling this. Returns a new DataFrame; `df` itself is not mutated.
    """
    df = df.copy()
    grouped = df.groupby("cc_num", group_keys=False)

    velocity = grouped.apply(_rolling_counts_and_sums)
    df = df.join(velocity)
    df["CC_TXN_COUNT_1H"] = df["CC_TXN_COUNT_1H"].fillna(0).astype(int)
    df["CC_TXN_COUNT_24H"] = df["CC_TXN_COUNT_24H"].fillna(0).astype(int)
    df["CC_AMT_SUM_24H"] = df["CC_AMT_SUM_24H"].fillna(0.0).astype(float)

    prior_means = grouped.apply(_expanding_prior_means)
    df = df.join(prior_means)
    df["AMT_DEVIATION_FROM_CC_AVG"] = df["amt"] - df["CC_AMT_AVG_PRIOR"]
    df["DISTANCE_FROM_USUAL_MERCHANT_KM"] = haversine_km(
        df["CC_USUAL_MERCH_LAT"], df["CC_USUAL_MERCH_LONG"], df["merch_lat"], df["merch_long"]
    )

    df["CC_SECONDS_SINCE_LAST_TXN"] = (
        df.groupby("cc_num")["trans_date_trans_time"].diff().dt.total_seconds()
    )

    return df
