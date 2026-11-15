"""Replay requests carry exactly the history the batch path used (ADR-0016).

A replayed request is only a fair stand-in for a test-split applicant if the API, given that
payload, assembles the same features training did. Rebuilding the per-applicant tables from each
payload and running `assemble_features` on them must reproduce the batch features row for row.
"""

from __future__ import annotations

import pandas as pd

from bankml.features.credit.anchor import compute_application_dates
from bankml.features.credit.pipeline import BASE_APPLICANT_COLUMNS, assemble_features
from bankml.features.credit.replay import build_requests, select_replay_applicants
from bankml.serving.app import CreditPredictionRequest
from tests.fixtures.credit.leakage_fixture import CONFIG, raw_tables

_HISTORY = [
    "bureau",
    "bureau_balance",
    "previous_application",
    "POS_CASH_balance",
    "installments_payments",
    "credit_card_balance",
]


def _dates(tables):
    anchor = CONFIG["synthetic_anchor"]
    return compute_application_dates(tables["application_train"], anchor["start"], anchor["end"])


def test_selects_only_test_split_applicants_in_date_order():
    tables = raw_tables()
    dates = _dates(tables)
    selected = select_replay_applicants(dates, CONFIG["split"], n=10)

    # The fixture anchors applicant 1 on 2020-01-01 (train) and applicant 2 on 2020-01-11 (test).
    assert list(selected.index) == [2]
    assert selected.is_monotonic_increasing


def test_spaces_a_smaller_sample_across_the_whole_window():
    dates = pd.Series(pd.date_range("2020-01-09", periods=100, freq="h"), index=range(100, 200))
    dates.index.name = "SK_ID_CURR"
    selected = select_replay_applicants(dates, CONFIG["split"], n=5)

    assert len(selected) == 5
    assert selected.index[0] == 100
    assert selected.index[-1] == 199


def test_payload_rebuilds_the_batch_features_for_each_applicant():
    tables = raw_tables()
    dates = _dates(tables)
    batch = assemble_features(tables, dates)
    history = {name: tables[name] for name in _HISTORY}
    application_df = tables["application_train"][["SK_ID_CURR", *BASE_APPLICANT_COLUMNS]]

    for payload in build_requests(application_df, history, dates):
        # The payload must parse as an API request at all.
        CreditPredictionRequest.model_validate(payload)

        applicant_id = payload["applicant_id"]
        # The API coerces through its Pandera contracts; the dtypes here stand in for that.
        single = {
            "application_train": pd.DataFrame(
                [{"SK_ID_CURR": applicant_id, **payload["applicant"]}]
            ).astype(application_df.dtypes.to_dict())
        }
        for name in _HISTORY:
            single[name] = pd.DataFrame(payload[name], columns=tables[name].columns).astype(
                tables[name].dtypes.to_dict()
            )
        serving_dates = pd.Series({applicant_id: pd.Timestamp(payload["decision_date"])})
        serving_dates.index.name = "SK_ID_CURR"

        expected = batch[batch["SK_ID_CURR"] == applicant_id].reset_index(drop=True)
        actual = assemble_features(single, serving_dates)
        pd.testing.assert_frame_equal(expected, actual, check_dtype=False)
