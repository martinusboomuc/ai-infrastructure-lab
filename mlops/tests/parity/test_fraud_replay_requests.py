"""Fraud replay requests reproduce the batch features through the API's own path (ADR-0023).

A replayed transaction is a fair stand-in only if the API, given that payload, assembles the same
features training did. The payload goes through the request model and the API's frame builder,
then `assemble_features`; the scored row must equal the batch row. Every fixture transaction is
used, including t4, whose previous transaction is older than the history window.
"""

from __future__ import annotations

import pandas as pd

from bankml.features.fraud.pipeline import assemble_features, build_features
from bankml.features.fraud.replay import build_requests, select_replay_transactions
from bankml.serving.app import FraudPredictionRequest, _build_fraud_frame
from tests.fixtures.fraud.leakage_fixture import CONFIG, raw_tables


def _transactions() -> pd.DataFrame:
    transactions = raw_tables()["fraudTrain"].drop(columns=["is_fraud"])
    transactions["trans_date_trans_time"] = pd.to_datetime(transactions["trans_date_trans_time"])
    return transactions


def test_selects_only_test_split_transactions_in_time_order():
    selected = select_replay_transactions(_transactions(), CONFIG["split"], n=10)

    # The fixture's test window starts on 2020-01-03: only t4 falls in it.
    assert list(selected["trans_num"]) == ["t4"]


def test_payload_rebuilds_the_batch_features_for_each_transaction():
    transactions = _transactions()
    batch = build_features(raw_tables(), CONFIG).drop(columns=["TARGET", "SPLIT", "IS_MATURE"])

    payloads = list(build_requests(transactions, transactions))
    assert len(payloads) == len(transactions)
    for payload in payloads:
        request = FraudPredictionRequest.model_validate(payload)
        features = assemble_features(_build_fraud_frame(request))

        trans_num = payload["transaction_id"]
        actual = features[features["trans_num"] == trans_num].reset_index(drop=True)
        expected = batch[batch["trans_num"] == trans_num].reset_index(drop=True)
        pd.testing.assert_frame_equal(expected, actual, check_dtype=False)


def test_history_stops_at_the_window():
    payloads = {p["transaction_id"]: p for p in build_requests(_transactions(), _transactions())}

    # t3 sees t0, t1 and t2; t4 is 44 days after t3, so it carries none.
    assert len(payloads["t3"]["history"]) == 3
    assert payloads["t4"]["history"] == []
