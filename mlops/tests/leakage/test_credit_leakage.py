"""ADR-0004's leakage test for Credit Risk: features built from the full tables must equal
features built from tables independently pre-truncated at each application's own decision date.

Uses the synthetic fixture from ADR-0007 (tests/fixtures/credit/), never real data, so this
runs from a clean clone with no dependency on the private DVC remote.
"""

import pandas as pd
from tests.fixtures.credit.leakage_fixture import CONFIG, raw_tables

from bankml.features.credit.anchor import compute_application_dates, derive_record_timestamps
from bankml.features.credit.pipeline import build_features

# Mirrors each aggregate function's own as-of column choice (src/bankml/features/credit/
# aggregates.py) so this test can independently pre-truncate tables. Deliberately not imported
# from aggregates.py: reusing that choice as a plain constant is fine, but the filtering itself
# is re-derived here rather than calling into aggregates.py's private filter helper.
_AS_OF_COLUMNS = {
    "bureau": {"days_col": "DAYS_CREDIT"},
    "previous_application": {"days_col": "DAYS_DECISION"},
    "POS_CASH_balance": {"months_col": "MONTHS_BALANCE"},
    "credit_card_balance": {"months_col": "MONTHS_BALANCE"},
}


def _truncate_application_keyed_table(df, table_name, application_dates):
    kwargs = _AS_OF_COLUMNS[table_name]
    record_ts = derive_record_timestamps(df, "SK_ID_CURR", application_dates, **kwargs)
    cutoff = df["SK_ID_CURR"].map(application_dates)
    return df[record_ts < cutoff].reset_index(drop=True)


def _truncate_installments(df, application_dates):
    effective_days = df["DAYS_ENTRY_PAYMENT"].fillna(df["DAYS_INSTALMENT"])
    working = df.assign(_EFFECTIVE_DAYS=effective_days)
    record_ts = derive_record_timestamps(
        working, "SK_ID_CURR", application_dates, days_col="_EFFECTIVE_DAYS"
    )
    cutoff = working["SK_ID_CURR"].map(application_dates)
    valid = working[record_ts < cutoff]
    return valid.drop(columns=["_EFFECTIVE_DAYS"]).reset_index(drop=True)


def _truncate_bureau_balance(bureau_balance_df, bureau_df, application_dates):
    bureau_to_curr = bureau_df.set_index("SK_ID_BUREAU")["SK_ID_CURR"]
    curr = bureau_balance_df["SK_ID_BUREAU"].map(bureau_to_curr)
    with_curr = bureau_balance_df.assign(SK_ID_CURR=curr).dropna(subset=["SK_ID_CURR"])
    with_curr["SK_ID_CURR"] = with_curr["SK_ID_CURR"].astype(bureau_df["SK_ID_CURR"].dtype)
    record_ts = derive_record_timestamps(
        with_curr, "SK_ID_CURR", application_dates, months_col="MONTHS_BALANCE"
    )
    cutoff = with_curr["SK_ID_CURR"].map(application_dates)
    valid = with_curr[record_ts < cutoff]
    return valid.drop(columns=["SK_ID_CURR"]).reset_index(drop=True)


def _manually_truncate_tables(tables, application_dates):
    truncated = dict(tables)
    truncated["bureau"] = _truncate_application_keyed_table(
        tables["bureau"], "bureau", application_dates
    )
    truncated["bureau_balance"] = _truncate_bureau_balance(
        tables["bureau_balance"], tables["bureau"], application_dates
    )
    truncated["previous_application"] = _truncate_application_keyed_table(
        tables["previous_application"], "previous_application", application_dates
    )
    truncated["POS_CASH_balance"] = _truncate_application_keyed_table(
        tables["POS_CASH_balance"], "POS_CASH_balance", application_dates
    )
    truncated["installments_payments"] = _truncate_installments(
        tables["installments_payments"], application_dates
    )
    truncated["credit_card_balance"] = _truncate_application_keyed_table(
        tables["credit_card_balance"], "credit_card_balance", application_dates
    )
    return truncated


def _application_dates(tables):
    anchor = CONFIG["synthetic_anchor"]
    return compute_application_dates(tables["application_train"], anchor["start"], anchor["end"])


def test_full_and_truncated_tables_produce_identical_features():
    tables = raw_tables()
    application_dates = _application_dates(tables)
    truncated_tables = _manually_truncate_tables(tables, application_dates)

    expected = build_features(truncated_tables, CONFIG)
    actual = build_features(tables, CONFIG)

    pd.testing.assert_frame_equal(expected, actual)


def test_fixture_has_teeth_the_future_bureau_record_would_change_a_naive_aggregate():
    tables = raw_tables()
    bureau = tables["bureau"]

    naive_count_for_id_1 = bureau[bureau["SK_ID_CURR"] == 1].shape[0]
    correct_features = build_features(tables, CONFIG).set_index("SK_ID_CURR")
    correct_count_for_id_1 = int(correct_features.loc[1, "BUREAU_COUNT"])

    assert naive_count_for_id_1 == 2
    assert correct_count_for_id_1 == 1
