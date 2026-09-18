from bankml.registry.model_card import generate_model_card

METRICS = {
    "train": {
        "pr_auc": 0.22,
        "roc_auc": 0.74,
        "recall_at_target_fpr": 0.23,
        "alert_volume_fraction": 0.10,
        "expected_cost": 100.0,
    }
}
SLICE_METRICS = {
    "train": {
        "slices": {
            "CODE_GENDER": {
                "M": {"n": 100, "pr_auc": 0.21, "within_tolerance": True},
                "F": {"n": 100, "pr_auc": None, "within_tolerance": None},
            }
        }
    }
}


def test_model_card_contains_required_sections():
    card = generate_model_card("credit", "champion", "scorecard", METRICS, SLICE_METRICS)

    assert "# Model Card: credit — champion (scorecard)" in card
    assert "## Metrics by split" in card
    assert "## Slice metrics" in card
    assert "## Known limitations" in card


def test_model_card_reports_metrics_and_slice_status():
    card = generate_model_card("credit", "champion", "scorecard", METRICS, SLICE_METRICS)

    assert "0.2200" in card  # PR-AUC
    assert "pass" in card  # M's within_tolerance=True
    assert "N/A (single class)" in card  # F's within_tolerance=None
