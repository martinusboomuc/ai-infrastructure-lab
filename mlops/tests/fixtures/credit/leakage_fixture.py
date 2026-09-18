"""Synthetic multi-table Credit Risk fixture for the leakage test (ADR-0007).

Fabricated data, not a slice of the real Kaggle dataset — matches real column names and the
same "relative to current application" semantics, deliberately including one auxiliary record
dated *after* its own application's synthetic decision date, so the leakage test exercises the
as-of boundary instead of passing vacuously.

SK_ID_CURR=1 gets a legitimate prior bureau record (DAYS_CREDIT=-100) and a deliberately
impossible future one (DAYS_CREDIT=+50) attached to a different SK_ID_BUREAU. A correct as-of
aggregation must count only the first; a naive, unfiltered one would count both.
"""

import pandas as pd

CONFIG = {
    "synthetic_anchor": {"start": "2020-01-01", "end": "2020-01-11"},
    "split": {
        "train": {"from": "2020-01-01", "to": "2020-01-05"},
        "gap_days": 1,
        "validation": {"from": "2020-01-06", "to": "2020-01-08"},
        "test": {"from": "2020-01-09", "to": "2020-01-15"},
    },
    "label": {"maturity_days": 1},
}


def raw_tables() -> dict[str, pd.DataFrame]:
    application_train = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "TARGET": [0, 1],
        }
    )

    bureau = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_BUREAU": [10, 11, 12],
            "DAYS_CREDIT": [-100, 50, -30],  # id=1's second row (+50) is the future leak
            "AMT_CREDIT_SUM": [1000.0, 99999.0, 500.0],
            "CREDIT_ACTIVE": ["Closed", "Active", "Active"],
        }
    )

    bureau_balance = pd.DataFrame(
        {
            "SK_ID_BUREAU": [10, 11],
            "MONTHS_BALANCE": [-2, 0],  # SK_ID_BUREAU=11 at month 0 == application date, excluded
            "STATUS": ["C", "0"],
        }
    )

    previous_application = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "SK_ID_PREV": [200, 201],
            "DAYS_DECISION": [-50, -20],
            "AMT_CREDIT": [5000.0, 3000.0],
            "NAME_CONTRACT_STATUS": ["Approved", "Refused"],
        }
    )

    pos_cash_balance = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "SK_ID_PREV": [200, 201],
            "MONTHS_BALANCE": [-1, -1],
            "CNT_INSTALMENT": [12, 6],
        }
    )

    installments_payments = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "SK_ID_PREV": [200, 201],
            "DAYS_INSTALMENT": [-40, -10],
            "DAYS_ENTRY_PAYMENT": [-41, None],
            "AMT_PAYMENT": [416.0, 500.0],
        }
    )

    credit_card_balance = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "SK_ID_PREV": [200, 201],
            "MONTHS_BALANCE": [-1, -1],
            "AMT_BALANCE": [100.0, 200.0],
        }
    )

    return {
        "application_train": application_train,
        "bureau": bureau,
        "bureau_balance": bureau_balance,
        "previous_application": previous_application,
        "POS_CASH_balance": pos_cash_balance,
        "installments_payments": installments_payments,
        "credit_card_balance": credit_card_balance,
    }
