"""ADR-0008: synthetic application-date anchor for Home Credit's relative timestamps.

Credit-Risk-specific, per ADR-0002 — this construction exists because Home Credit's raw data
carries no real calendar date anywhere, not because any other domain needs it. Never import
this from core.
"""

from __future__ import annotations

import pandas as pd

AVERAGE_DAYS_PER_MONTH = 30.44  # Home Credit's MONTHS_BALANCE is coarse; the anchor is already
# synthetic (ADR-0008), so an average-month approximation is consistent with that, not a new
# source of imprecision.


def compute_application_dates(
    application_df: pd.DataFrame, anchor_start: str, anchor_end: str
) -> pd.Series:
    """Assign each SK_ID_CURR a synthetic APPLICATION_DATE (ADR-0008).

    Ranks applications by SK_ID_CURR ascending and linearly maps rank onto
    [anchor_start, anchor_end]. Returned Series is indexed by SK_ID_CURR.
    """
    ids = application_df["SK_ID_CURR"].sort_values().reset_index(drop=True)
    n = len(ids)
    start = pd.Timestamp(anchor_start)
    end = pd.Timestamp(anchor_end)
    if n == 1:
        dates = pd.Series([start], index=[ids.iloc[0]])
    else:
        span = end - start
        fractions = pd.Series(range(n)) / (n - 1)
        dates = pd.Series((start + fractions * span).values, index=ids)
    dates.index.name = "SK_ID_CURR"
    return dates


def derive_record_timestamps(
    df: pd.DataFrame,
    sk_id_curr_col: str,
    application_dates: pd.Series,
    *,
    days_col: str | None = None,
    months_col: str | None = None,
) -> pd.Series:
    """Derive each row's own timestamp from its SK_ID_CURR's APPLICATION_DATE plus its offset.

    Exactly one of days_col/months_col must be given, matching the column's documented
    "relative to current application" semantics (verified against
    HomeCredit_columns_description.csv in ADR-0008, not assumed).
    """
    if (days_col is None) == (months_col is None):
        raise ValueError("exactly one of days_col or months_col must be given")

    base = df[sk_id_curr_col].map(application_dates)
    if days_col is not None:
        offset = pd.to_timedelta(df[days_col], unit="D")
    else:
        offset = pd.to_timedelta(df[months_col] * AVERAGE_DAYS_PER_MONTH, unit="D")
    return base + offset
