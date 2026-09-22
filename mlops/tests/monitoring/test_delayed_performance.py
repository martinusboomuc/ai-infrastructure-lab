"""Delayed-label performance tests (Phase 5). Synthetic fixtures (ADR-0007's pattern) — every
test mocks `read_all_records` and `load_ground_truth` directly, so none of this depends on real
data, a real prediction log, or a real MLflow server.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd

from bankml.monitoring.delayed_performance import compute_delayed_performance

MATURITY_DAYS = 540
NOW = datetime(2026, 9, 22, tzinfo=UTC)


def _record(applicant_id: int, decision: str, score: float, days_ago: int) -> dict:
    return {
        "request_id": f"req-{applicant_id}",
        "applicant_id": applicant_id,
        "score": score,
        "decision": decision,
        "timestamp": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_no_matured_predictions_when_everything_is_too_recent():
    records = [_record(1, "pass", 0.1, days_ago=10)]
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth") as mock_gt,
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["status"] == "no_matured_predictions"
    assert result["n_logged"] == 1
    mock_gt.assert_not_called()  # no point loading ground truth for nothing matured yet


def test_no_matured_predictions_when_the_log_is_empty():
    with patch("bankml.monitoring.delayed_performance.read_all_records", return_value=[]):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["status"] == "no_matured_predictions"
    assert result["n_logged"] == 0


def test_no_labeled_matured_predictions_when_applicant_ids_do_not_match_ground_truth():
    records = [_record(999_001, "pass", 0.1, days_ago=600)]  # matured, but a synthetic test ID
    ground_truth = pd.Series({1: 0, 2: 1}, name="TARGET")
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["status"] == "no_labeled_matured_predictions"
    assert result["n_matured"] == 1


def test_a_correct_flag_counts_as_a_true_positive():
    records = [_record(1, "flag", 0.9, days_ago=600)]
    ground_truth = pd.Series({1: 1}, name="TARGET")  # actually defaulted — flagging was right
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["status"] == "ok"
    assert result["true_positive"] == 1
    assert result["false_negative"] == 0
    assert result["accuracy"] == 1.0


def test_a_missed_default_counts_as_a_false_negative():
    records = [_record(1, "pass", 0.05, days_ago=600)]
    ground_truth = pd.Series({1: 1}, name="TARGET")  # defaulted, but the model said pass
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["status"] == "ok"
    assert result["false_negative"] == 1
    assert result["recall"] == 0.0


def test_only_matured_and_labeled_predictions_are_counted_not_the_rest():
    records = [
        _record(1, "flag", 0.9, days_ago=600),  # matured + labeled
        _record(2, "pass", 0.1, days_ago=5),  # too recent
        _record(3, "pass", 0.1, days_ago=600),  # matured, but no ground truth
    ]
    ground_truth = pd.Series({1: 1}, name="TARGET")
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert result["n_logged"] == 3
    assert result["n_matured"] == 2
    assert result["n_labeled"] == 1


def test_pr_auc_and_roc_auc_included_when_both_classes_are_present():
    records = [
        _record(1, "flag", 0.9, days_ago=600),
        _record(2, "pass", 0.1, days_ago=600),
    ]
    ground_truth = pd.Series({1: 1, 2: 0}, name="TARGET")
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert "pr_auc" in result
    assert "roc_auc" in result


def test_pr_auc_is_omitted_not_faked_when_only_one_class_is_present():
    records = [_record(1, "flag", 0.9, days_ago=600)]
    ground_truth = pd.Series({1: 1}, name="TARGET")
    with (
        patch("bankml.monitoring.delayed_performance.read_all_records", return_value=records),
        patch("bankml.monitoring.delayed_performance.load_ground_truth", return_value=ground_truth),
    ):
        result = compute_delayed_performance("credit", MATURITY_DAYS, as_of=NOW)

    assert "pr_auc" not in result
    assert "roc_auc" not in result
