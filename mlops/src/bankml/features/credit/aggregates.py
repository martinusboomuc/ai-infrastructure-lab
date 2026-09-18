"""As-of aggregation functions for the Home Credit auxiliary tables.

Every function here follows the same shape: derive each row's own timestamp (anchor.py),
keep only rows strictly before the owning application's own APPLICATION_DATE, then aggregate.
That filter line is exactly what tests/leakage/test_credit_leakage.py exists to prove is both
present and correct.

Feature scope is deliberately modest (2-3 aggregates per table) — this proves the point-in-time
correctness mechanism works end to end, it is not an exhaustive feature set. Phase 3 iterates on
breadth once there is a model to iterate against.
"""

from __future__ import annotations

import pandas as pd

from bankml.features.credit.anchor import derive_record_timestamps


def _as_of_filter(
    record_ts: pd.Series, sk_id_curr: pd.Series, application_dates: pd.Series
) -> pd.Series:
    cutoff = sk_id_curr.map(application_dates)
    return record_ts < cutoff


def bureau_aggregates(
    bureau_df: pd.DataFrame, bureau_balance_df: pd.DataFrame, application_dates: pd.Series
) -> pd.DataFrame:
    record_ts = derive_record_timestamps(
        bureau_df, "SK_ID_CURR", application_dates, days_col="DAYS_CREDIT"
    )
    valid = bureau_df[_as_of_filter(record_ts, bureau_df["SK_ID_CURR"], application_dates)]

    agg = valid.groupby("SK_ID_CURR").agg(
        BUREAU_COUNT=("SK_ID_BUREAU", "count"),
        BUREAU_AMT_CREDIT_SUM_MEAN=("AMT_CREDIT_SUM", "mean"),
    )
    active_count = (
        valid[valid["CREDIT_ACTIVE"] == "Active"]
        .groupby("SK_ID_CURR")
        .size()
        .rename("BUREAU_ACTIVE_COUNT")
    )
    agg = agg.join(active_count, how="left")
    agg["BUREAU_ACTIVE_COUNT"] = agg["BUREAU_ACTIVE_COUNT"].fillna(0).astype(int)

    # bureau_balance has no SK_ID_CURR of its own — resolve it through bureau's SK_ID_BUREAU
    # first. Using the full (unfiltered) bureau table for that mapping is fine: which SK_ID_CURR
    # owns which SK_ID_BUREAU isn't a leakage concern, only each balance record's own timestamp.
    bureau_to_curr = bureau_df.set_index("SK_ID_BUREAU")["SK_ID_CURR"]
    balance_curr = bureau_balance_df["SK_ID_BUREAU"].map(bureau_to_curr)
    balance_with_curr = bureau_balance_df.assign(SK_ID_CURR=balance_curr).dropna(
        subset=["SK_ID_CURR"]
    )
    curr_dtype = bureau_df["SK_ID_CURR"].dtype
    balance_with_curr["SK_ID_CURR"] = balance_with_curr["SK_ID_CURR"].astype(curr_dtype)

    balance_record_ts = derive_record_timestamps(
        balance_with_curr, "SK_ID_CURR", application_dates, months_col="MONTHS_BALANCE"
    )
    balance_valid = balance_with_curr[
        _as_of_filter(balance_record_ts, balance_with_curr["SK_ID_CURR"], application_dates)
    ]
    balance_count = balance_valid.groupby("SK_ID_CURR").size().rename("BUREAU_BALANCE_COUNT")
    agg = agg.join(balance_count, how="left")
    agg["BUREAU_BALANCE_COUNT"] = agg["BUREAU_BALANCE_COUNT"].fillna(0).astype(int)

    return agg


def previous_application_aggregates(
    previous_application_df: pd.DataFrame, application_dates: pd.Series
) -> pd.DataFrame:
    record_ts = derive_record_timestamps(
        previous_application_df, "SK_ID_CURR", application_dates, days_col="DAYS_DECISION"
    )
    valid = previous_application_df[
        _as_of_filter(record_ts, previous_application_df["SK_ID_CURR"], application_dates)
    ]

    agg = valid.groupby("SK_ID_CURR").agg(
        PREV_APP_COUNT=("SK_ID_PREV", "count"),
        PREV_APP_AMT_CREDIT_MEAN=("AMT_CREDIT", "mean"),
    )
    approved_count = (
        valid[valid["NAME_CONTRACT_STATUS"] == "Approved"]
        .groupby("SK_ID_CURR")
        .size()
        .rename("PREV_APP_APPROVED_COUNT")
    )
    agg = agg.join(approved_count, how="left")
    agg["PREV_APP_APPROVED_COUNT"] = agg["PREV_APP_APPROVED_COUNT"].fillna(0).astype(int)
    return agg


def pos_cash_balance_aggregates(
    pos_cash_df: pd.DataFrame, application_dates: pd.Series
) -> pd.DataFrame:
    record_ts = derive_record_timestamps(
        pos_cash_df, "SK_ID_CURR", application_dates, months_col="MONTHS_BALANCE"
    )
    sk_id_curr = pos_cash_df["SK_ID_CURR"]
    valid = pos_cash_df[_as_of_filter(record_ts, sk_id_curr, application_dates)]
    return valid.groupby("SK_ID_CURR").agg(
        POS_CASH_COUNT=("SK_ID_PREV", "count"),
        POS_CASH_CNT_INSTALMENT_MEAN=("CNT_INSTALMENT", "mean"),
    )


def installments_payments_aggregates(
    installments_df: pd.DataFrame, application_dates: pd.Series
) -> pd.DataFrame:
    entry_payment = installments_df["DAYS_ENTRY_PAYMENT"]
    effective_days = entry_payment.fillna(installments_df["DAYS_INSTALMENT"])
    working = installments_df.assign(_EFFECTIVE_DAYS=effective_days)
    record_ts = derive_record_timestamps(
        working, "SK_ID_CURR", application_dates, days_col="_EFFECTIVE_DAYS"
    )
    valid = working[_as_of_filter(record_ts, working["SK_ID_CURR"], application_dates)]
    return valid.groupby("SK_ID_CURR").agg(
        INSTALLMENTS_COUNT=("SK_ID_PREV", "count"),
        INSTALLMENTS_AMT_PAYMENT_SUM=("AMT_PAYMENT", "sum"),
    )


def credit_card_balance_aggregates(
    credit_card_df: pd.DataFrame, application_dates: pd.Series
) -> pd.DataFrame:
    record_ts = derive_record_timestamps(
        credit_card_df, "SK_ID_CURR", application_dates, months_col="MONTHS_BALANCE"
    )
    sk_id_curr = credit_card_df["SK_ID_CURR"]
    valid = credit_card_df[_as_of_filter(record_ts, sk_id_curr, application_dates)]
    return valid.groupby("SK_ID_CURR").agg(
        CREDIT_CARD_COUNT=("SK_ID_PREV", "count"),
        CREDIT_CARD_AMT_BALANCE_MEAN=("AMT_BALANCE", "mean"),
    )
