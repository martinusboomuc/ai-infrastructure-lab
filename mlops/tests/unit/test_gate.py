from bankml.registry.gate import evaluate_gate

CONFIG = {"evaluation": {"gate": {"min_pr_auc": 0.15}}}

GOOD_METRICS = {"pr_auc": 0.22, "roc_auc": 0.74}
GOOD_SLICES = {
    "slices": {
        "CODE_GENDER": {
            "M": {"n": 100, "pr_auc": 0.21, "within_tolerance": True},
            "F": {"n": 100, "pr_auc": 0.20, "within_tolerance": True},
        }
    }
}
GOOD_REASON_CODES = [{"row_index": 1, "contributions": []}]
GOOD_MODEL_CARD = "# Model Card\n\nSome content."


def test_a_healthy_model_passes_every_check():
    result = evaluate_gate(GOOD_METRICS, GOOD_SLICES, GOOD_REASON_CODES, GOOD_MODEL_CARD, CONFIG)
    assert result.passed is True
    assert result.reasons == []


def test_rejects_pr_auc_below_the_configured_floor():
    degraded = {**GOOD_METRICS, "pr_auc": 0.05}
    result = evaluate_gate(degraded, GOOD_SLICES, GOOD_REASON_CODES, GOOD_MODEL_CARD, CONFIG)
    assert result.passed is False
    assert any("PR-AUC" in reason for reason in result.reasons)


def test_rejects_a_slice_that_exceeds_tolerance():
    degraded_slices = {
        "slices": {"CODE_GENDER": {"M": {"n": 100, "pr_auc": 0.05, "within_tolerance": False}}}
    }
    result = evaluate_gate(
        GOOD_METRICS, degraded_slices, GOOD_REASON_CODES, GOOD_MODEL_CARD, CONFIG
    )
    assert result.passed is False
    assert any("tolerance" in reason for reason in result.reasons)


def test_rejects_missing_reason_codes():
    result = evaluate_gate(GOOD_METRICS, GOOD_SLICES, [], GOOD_MODEL_CARD, CONFIG)
    assert result.passed is False
    assert any("reason codes" in reason for reason in result.reasons)


def test_rejects_an_empty_model_card():
    result = evaluate_gate(GOOD_METRICS, GOOD_SLICES, GOOD_REASON_CODES, "", CONFIG)
    assert result.passed is False
    assert any("model card" in reason for reason in result.reasons)
