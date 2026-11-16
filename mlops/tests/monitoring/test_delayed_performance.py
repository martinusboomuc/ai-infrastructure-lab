"""Production performance on replayed outcomes (ADR-0021). Synthetic records and outcomes, so
none of this needs a prediction log, the outcome blob or an MLflow server.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from bankml.monitoring.delayed_performance import compute_performance, select_window
from bankml.monitoring.outcomes import build_outcomes, replayed_applicant_ids

NOW = datetime(2026, 11, 30, tzinfo=UTC)
REFERENCE = {"roc_auc": 0.75, "pr_auc": 0.22}


def _record(applicant_id, score=0.1, days_ago=10, version="3", source="replay", decision="pass"):
    return {
        "request_id": f"req-{applicant_id}-{days_ago}",
        "applicant_id": applicant_id,
        "score": score,
        "decision": decision,
        "model_version": version,
        "traffic_source": source,
        "timestamp": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_the_window_keeps_only_replayed_predictions_by_the_version_with_known_outcomes():
    records = [
        _record(1, days_ago=10),
        _record(2, days_ago=3),  # outcome not known yet: served after the 7-day cut-off
        _record(3, days_ago=60),  # before the 30-day window
        _record(4, days_ago=10, version="1"),  # another version's prediction
        _record(5, days_ago=10, source="live"),  # live traffic has no outcome feed
    ]

    selected = select_window(records, "3", NOW, delay_days=7, window_days=30)

    assert [r["applicant_id"] for r in selected] == [1]


def _scored(n=1000, separation=1.5, seed=0):
    """Predictions where defaulters score higher by `separation` standard deviations."""
    rng = np.random.default_rng(seed)
    outcome = (rng.random(n) < 0.1).astype(int)
    raw = rng.normal(size=n) + separation * outcome
    score = 1 / (1 + np.exp(-raw))
    threshold = np.quantile(score, 0.9)
    records = [
        _record(i, score=float(s), decision="flag" if s >= threshold else "pass")
        for i, s in enumerate(score)
    ]
    return records, pd.Series(outcome, index=range(n))


def test_a_model_that_ranks_as_well_as_on_test_is_not_degraded():
    records, outcomes = _scored(separation=1.5)

    result = compute_performance(records, outcomes, REFERENCE)

    assert result["status"] == "ok"
    assert result["n_labeled"] == 1000
    assert result["alert_rate"] == pytest.approx(0.1, abs=0.01)
    assert result["roc_auc"] > 0.8
    assert result["degraded"] is False
    tp, fn = result["true_positive"], result["false_negative"]
    assert result["recall"] == pytest.approx(tp / (tp + fn))


def test_a_model_that_no_longer_ranks_is_degraded():
    records, outcomes = _scored(separation=0.0)

    result = compute_performance(records, outcomes, REFERENCE)

    assert result["roc_auc_drop"] > 0.05
    assert result["degraded"] is True


def test_too_few_outcomes_is_reported_not_measured():
    records, outcomes = _scored(n=200)

    result = compute_performance(records, outcomes, REFERENCE)

    assert result["status"] == "insufficient_outcomes"
    assert "roc_auc" not in result


def test_predictions_without_a_published_outcome_are_not_counted():
    records, outcomes = _scored()
    records.append(_record(999_999, score=0.99, decision="flag"))

    result = compute_performance(records, outcomes, REFERENCE)

    assert result["n_in_window"] == 1001
    assert result["n_labeled"] == 1000


def test_outcomes_cover_only_replayed_applicants_with_a_known_target():
    config = {"entity_key": "SK_ID_CURR", "target": "TARGET"}
    features = pd.DataFrame({"SK_ID_CURR": [1, 2, 3, 4], "TARGET": [0, 1, None, 1]})
    ids = replayed_applicant_ids(
        ['{"applicant_id": 1}', '{"applicant_id": 2}', '{"applicant_id": 3}']
    )

    outcomes = build_outcomes(features, ids, config)

    assert outcomes.to_dict("records") == [
        {"applicant_id": 1, "outcome": 0},
        {"applicant_id": 2, "outcome": 1},
    ]


def _pushed(result):
    from unittest.mock import patch

    from bankml.monitoring.delayed_performance import push_performance_metrics

    with patch("prometheus_client.push_to_gateway") as push:
        push_performance_metrics("credit", result, "http://pushgateway:9091")
    registry = push.call_args.kwargs["registry"]
    return {sample.name: sample.value for metric in registry.collect() for sample in metric.samples}


def test_a_run_without_enough_outcomes_still_publishes_what_is_known():
    result = {
        "status": "insufficient_outcomes",
        "model_version": "3",
        "test_roc_auc": 0.7469,
        "test_pr_auc": 0.2236,
        "n_labeled": 120,
        "n_positive": 9,
    }

    pushed = _pushed(result)

    assert pushed["bankml_performance_test_roc_auc"] == 0.7469
    assert pushed["bankml_performance_n_labeled"] == 120
    assert pushed["bankml_performance_measured"] == 0
    assert "bankml_performance_roc_auc" not in pushed
    assert "bankml_performance_last_run_timestamp_seconds" in pushed


def test_a_measured_run_publishes_the_live_metrics():
    records, outcomes = _scored()
    result = {"model_version": "3", **compute_performance(records, outcomes, REFERENCE)}

    pushed = _pushed(result)

    assert pushed["bankml_performance_measured"] == 1
    assert pushed["bankml_performance_roc_auc"] == result["roc_auc"]
    assert pushed["bankml_performance_roc_auc_drop"] == result["roc_auc_drop"]
