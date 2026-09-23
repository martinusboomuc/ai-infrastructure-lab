"""Synthetic Sparkov-shaped fixture for the fraud leakage test (ADR-0007, extended to Phase 6).

Fabricated data, not a slice of the real Kaggle dataset — matches real column names. cc_num=1 has
four transactions spaced to exercise both the 1h and 24h as-of windows (t1 is inside t0's 1h/24h
window; t2 is outside both t0's and t1's 1h window but inside their 24h window; t3 is outside
t0/t1's 24h window but inside t2's). cc_num=2 has two transactions close together, purely to prove
history features never leak across customers.
"""

import pandas as pd

CONFIG = {
    "split": {
        "train": {"from": "2020-01-01", "to": "2020-01-01"},
        "gap_days": 0,
        "validation": {"from": "2020-01-02", "to": "2020-01-02"},
        "test": {"from": "2020-01-03", "to": "2020-01-05"},
    },
    "label": {"maturity_days": 0, "as_of": "2020-01-05"},
}


def raw_tables() -> dict[str, pd.DataFrame]:
    transactions = pd.DataFrame(
        {
            "trans_num": ["t0", "t1", "t2", "t3", "s0", "s1"],
            "trans_date_trans_time": [
                "2020-01-01 00:00:00",
                "2020-01-01 00:30:00",  # 30 min after t0
                "2020-01-01 02:00:00",  # 2h after t0, 1.5h after t1
                "2020-01-02 01:00:00",  # 25h after t0, 23h after t2
                "2020-01-01 00:00:00",
                "2020-01-01 00:10:00",  # 10 min after s0
            ],
            "cc_num": [1, 1, 1, 1, 2, 2],
            "amt": [10.0, 20.0, 30.0, 40.0, 5.0, 7.0],
            "category": ["misc_net", "grocery_pos", "misc_net", "travel", "misc_net", "misc_net"],
            "lat": [36.0, 36.0, 36.0, 36.0, 40.0, 40.0],
            "long": [-81.0, -81.0, -81.0, -81.0, -75.0, -75.0],
            "merch_lat": [36.01, 36.02, 36.03, 36.04, 40.01, 40.02],
            "merch_long": [-81.01, -81.02, -81.03, -81.04, -75.01, -75.02],
            "is_fraud": [0, 0, 0, 1, 0, 0],
        }
    )
    return {"fraudTrain": transactions}
