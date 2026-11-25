"""As-of, point-in-time-correct customer/card (cc_num) history features for Sparkov transactions.

Every feature here is computed using only transactions strictly before the transaction's own
timestamp, for the same cc_num — never itself, never a same-timestamp or later one — and no
further back than `HISTORY_DAYS`. The bound is what lets serving work: a request carries the
card's own recent transactions (ADR-0009's pattern, ADR-0023), and a feature that read the whole
history would need every earlier transaction, about 2,200 on average, in every request.
tests/leakage/test_fraud_leakage.py is the enforcement mechanism (ADR-0007's pattern, adapted to
one flat table instead of Credit Risk's relational tables): a naive, unfiltered rolling window
would include the row's own transaction; this module's `closed="left"` rolling windows are
exactly what keeps that from happening.

DISTANCE_FROM_HOME_KM is deliberately NOT computed here — it needs only the row's own lat/long
and merch_lat/merch_long, carries no leakage risk, and lives directly in
pipeline.py's assemble_features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0
# The longest look-back of any feature. Serving needs a card's transactions from this window only.
HISTORY_DAYS = 30
_HISTORY_WINDOW = f"{HISTORY_DAYS}D"


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    lat1_r, lon1_r, lat2_r, lon2_r = (np.radians(x) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def _rolling_history(group: pd.DataFrame) -> pd.DataFrame:
    indexed = group.set_index("trans_date_trans_time")

    def rolling(column: str, window: str):
        return indexed[column].rolling(window, closed="left")

    return pd.DataFrame(
        {
            "CC_TXN_COUNT_1H": rolling("amt", "1h").count().to_numpy(),
            "CC_TXN_COUNT_24H": rolling("amt", "24h").count().to_numpy(),
            "CC_AMT_SUM_24H": rolling("amt", "24h").sum().to_numpy(),
            "CC_AMT_AVG_30D": rolling("amt", _HISTORY_WINDOW).mean().to_numpy(),
            "CC_AMT_STD_30D": rolling("amt", _HISTORY_WINDOW).std().to_numpy(),
            "CC_USUAL_MERCH_LAT": rolling("merch_lat", _HISTORY_WINDOW).mean().to_numpy(),
            "CC_USUAL_MERCH_LONG": rolling("merch_long", _HISTORY_WINDOW).mean().to_numpy(),
        },
        index=group.index,
    )


def _rolling_category_history(group: pd.DataFrame) -> pd.DataFrame:
    """The card's own history in the transaction's category: how often it bought there and how
    much it usually spent. A large travel purchase is ordinary for a card that travels and not
    for one that never has."""
    amounts = group.set_index("trans_date_trans_time")["amt"].rolling(
        _HISTORY_WINDOW, closed="left"
    )
    return pd.DataFrame(
        {
            "CC_CATEGORY_TXN_COUNT_30D": amounts.count().to_numpy(),
            "CC_CATEGORY_AMT_AVG_30D": amounts.mean().to_numpy(),
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

    history = grouped.apply(_rolling_history)
    df = df.join(history)
    df["CC_TXN_COUNT_1H"] = df["CC_TXN_COUNT_1H"].fillna(0).astype(int)
    df["CC_TXN_COUNT_24H"] = df["CC_TXN_COUNT_24H"].fillna(0).astype(int)
    df["CC_AMT_SUM_24H"] = df["CC_AMT_SUM_24H"].fillna(0.0).astype(float)

    df["AMT_DEVIATION_FROM_CC_AVG"] = df["amt"] - df["CC_AMT_AVG_30D"]
    # Missing with fewer than two earlier transactions, or when every one had the same amount.
    df["AMT_ZSCORE_30D"] = df["AMT_DEVIATION_FROM_CC_AVG"] / df["CC_AMT_STD_30D"].where(
        df["CC_AMT_STD_30D"] > 0
    )

    category_history = df.groupby(["cc_num", "category"], group_keys=False).apply(
        _rolling_category_history
    )
    df = df.join(category_history)
    df["CC_CATEGORY_TXN_COUNT_30D"] = df["CC_CATEGORY_TXN_COUNT_30D"].fillna(0).astype(int)
    df["AMT_DEVIATION_FROM_CC_CATEGORY_AVG"] = df["amt"] - df["CC_CATEGORY_AMT_AVG_30D"]
    df["DISTANCE_FROM_USUAL_MERCHANT_KM"] = haversine_km(
        df["CC_USUAL_MERCH_LAT"], df["CC_USUAL_MERCH_LONG"], df["merch_lat"], df["merch_long"]
    )

    # Missing, not the true gap, when the last transaction is older than the window: serving
    # cannot see further back, so training must not either.
    since_last = df.groupby("cc_num")["trans_date_trans_time"].diff()
    df["CC_SECONDS_SINCE_LAST_TXN"] = since_last.where(
        since_last <= pd.Timedelta(days=HISTORY_DAYS)
    ).dt.total_seconds()

    return df
