"""ADR-0004/ADR-0007's leakage test for Fraud: every customer-history feature must equal what an
independently-written, strictly-prior-only recomputation produces — a different code path
(plain per-row filtering) than velocity.py's own rolling implementation, so a bug that
looks-consistent-with-itself in velocity.py still gets caught here.

Uses the synthetic fixture from tests/fixtures/fraud/, never real data, so this runs from a clean
clone with no dependency on the private DVC remote.
"""

import numpy as np
import pandas as pd
from tests.fixtures.fraud.leakage_fixture import CONFIG, raw_tables

from bankml.features.fraud.pipeline import build_features
from bankml.features.fraud.velocity import HISTORY_DAYS, haversine_km


def _manually_compute_expected(transactions: pd.DataFrame) -> pd.DataFrame:
    df = transactions.copy()
    df["trans_date_trans_time"] = pd.to_datetime(df["trans_date_trans_time"])

    expected = {}
    for _cc_num, group in df.groupby("cc_num"):
        group = group.sort_values("trans_date_trans_time")
        rows = group.to_dict("records")
        for i, row in enumerate(rows):
            prior = rows[:i]
            t = row["trans_date_trans_time"]

            # velocity.py's rolling windows use closed="left": [t - window, t) — the boundary
            # exactly `window` ago is included, only the row's own timestamp is excluded. Hence
            # <=, not <, against the window width here.
            count_1h = sum(1 for p in prior if t - p["trans_date_trans_time"] <= pd.Timedelta("1h"))
            count_24h = sum(
                1 for p in prior if t - p["trans_date_trans_time"] <= pd.Timedelta("24h")
            )
            amt_sum_24h = sum(
                p["amt"] for p in prior if t - p["trans_date_trans_time"] <= pd.Timedelta("24h")
            )

            # The history window, closed on the left the same way.
            recent = [
                p
                for p in prior
                if t - p["trans_date_trans_time"] <= pd.Timedelta(days=HISTORY_DAYS)
            ]
            same_category = [p["amt"] for p in recent if p["category"] == row["category"]]
            amt_std = np.std([p["amt"] for p in recent], ddof=1) if len(recent) > 1 else np.nan
            if recent:
                amt_avg_prior = np.mean([p["amt"] for p in recent])
                usual_merch_lat = np.mean([p["merch_lat"] for p in recent])
                usual_merch_long = np.mean([p["merch_long"] for p in recent])
                seconds_since_last = (t - recent[-1]["trans_date_trans_time"]).total_seconds()
            else:
                amt_avg_prior = np.nan
                usual_merch_lat = np.nan
                usual_merch_long = np.nan
                seconds_since_last = np.nan

            expected[row["trans_num"]] = {
                "CC_TXN_COUNT_1H": count_1h,
                "CC_TXN_COUNT_24H": count_24h,
                "CC_AMT_SUM_24H": amt_sum_24h,
                "CC_AMT_AVG_30D": amt_avg_prior,
                "AMT_DEVIATION_FROM_CC_AVG": row["amt"] - amt_avg_prior,
                "AMT_ZSCORE_30D": (row["amt"] - amt_avg_prior) / amt_std
                if amt_std and amt_std > 0
                else np.nan,
                "CC_CATEGORY_TXN_COUNT_30D": len(same_category),
                "AMT_DEVIATION_FROM_CC_CATEGORY_AVG": row["amt"] - np.mean(same_category)
                if same_category
                else np.nan,
                "DISTANCE_FROM_USUAL_MERCHANT_KM": float(
                    haversine_km(
                        pd.Series([usual_merch_lat]),
                        pd.Series([usual_merch_long]),
                        pd.Series([row["merch_lat"]]),
                        pd.Series([row["merch_long"]]),
                    ).iloc[0]
                )
                if recent
                else np.nan,
                "CC_SECONDS_SINCE_LAST_TXN": seconds_since_last,
            }

    return pd.DataFrame.from_dict(expected, orient="index")


def test_history_features_match_an_independently_recomputed_as_of_calculation():
    tables = raw_tables()
    actual = build_features(tables, CONFIG).set_index("trans_num")
    expected = _manually_compute_expected(tables["fraudTrain"])

    columns = list(expected.columns)
    pd.testing.assert_frame_equal(
        actual.loc[expected.index, columns], expected[columns], check_dtype=False
    )


def test_fixture_has_teeth_a_naive_unfiltered_count_would_change_t0s_feature():
    tables = raw_tables()
    naive_count_for_cc1 = (tables["fraudTrain"]["cc_num"] == 1).sum()

    features = build_features(tables, CONFIG).set_index("trans_num")
    correct_count_for_t0 = int(features.loc["t0", "CC_TXN_COUNT_24H"])

    assert naive_count_for_cc1 == 5
    assert correct_count_for_t0 == 0


def test_1h_and_24h_windows_are_distinct_boundaries():
    tables = raw_tables()
    features = build_features(tables, CONFIG).set_index("trans_num")

    # t2 is 90 minutes after t1 and 2 hours after t0: outside the 1h window of both, but inside
    # the 24h window of both.
    assert features.loc["t2", "CC_TXN_COUNT_1H"] == 0
    assert features.loc["t2", "CC_TXN_COUNT_24H"] == 2

    # t3 is 25h after t0 (outside its 24h window) but 23h after t2 (inside its 24h window).
    assert features.loc["t3", "CC_TXN_COUNT_24H"] == 1


def test_history_never_leaks_across_customers():
    tables = raw_tables()
    features = build_features(tables, CONFIG).set_index("trans_num")

    # s0/s1 belong to cc_num=2 — cc_num=1's four transactions must never appear in their history.
    assert features.loc["s0", "CC_TXN_COUNT_24H"] == 0
    assert features.loc["s1", "CC_TXN_COUNT_24H"] == 1


def test_history_older_than_the_window_is_not_seen():
    tables = raw_tables()
    features = build_features(tables, CONFIG).set_index("trans_num")

    # t4 is 44 days after cc_num=1's previous transaction: what serving cannot see (ADR-0023),
    # training must not use either.
    assert np.isnan(features.loc["t4", "CC_AMT_AVG_30D"])
    assert np.isnan(features.loc["t4", "CC_SECONDS_SINCE_LAST_TXN"])
    assert np.isnan(features.loc["t4", "DISTANCE_FROM_USUAL_MERCHANT_KM"])
