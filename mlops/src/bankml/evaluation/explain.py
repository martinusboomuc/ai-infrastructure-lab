"""SHAP reason codes for both champion and challenger (roadmap item, ADR-0005).

Each model gets the SHAP explainer that's actually correct for its structure — not a slow
generic fallback. For the scorecard this is close to redundant with its own native additive
WoE structure (every bin's contribution is already directly readable); it's still produced so
both models expose reason codes through the same interface, and so the asymmetry ADR-0005
predicts (the GBM's explanations are an approximation, the scorecard's aren't) is visible in the
same format rather than asserted.

Computed on a sample, not the full dataset — reason codes are a per-prediction, serving-time
concern (Phase 4); this demonstrates the mechanism works, not a batch job over 300k+ rows.
"""

from __future__ import annotations

import shap

DEFAULT_SAMPLE_SIZE = 50


def compute_reason_codes(
    model, model_type: str, X, top_n: int = 5, sample_size: int = DEFAULT_SAMPLE_SIZE
) -> list[dict]:
    """Top-`top_n` contributing features per sampled row, as a list of
    {row_index, contributions: [{feature, shap_value}, ...]}.
    """
    sample = X.sample(n=min(sample_size, len(X)), random_state=42)

    if model_type == "scorecard":
        X_woe = model.binning_process.transform(sample)
        explainer = shap.LinearExplainer(model.logistic_regression, X_woe)
        shap_values = explainer.shap_values(X_woe)
        feature_names = list(sample.columns)
    elif model_type == "lightgbm":
        explainer = shap.TreeExplainer(model)
        raw_shap = explainer.shap_values(sample)
        # LightGBM's sklearn API can return a single array (binary) or a list per class.
        shap_values = raw_shap[1] if isinstance(raw_shap, list) else raw_shap
        feature_names = list(sample.columns)
    elif model_type == "logistic_regression":
        # model is the Pipeline from training/logistic.py — SHAP needs the fitted linear model
        # and a background/explain set in the *same already-encoded* numeric space, not the
        # raw pre-preprocessing columns LinearExplainer would otherwise see.
        preprocessor = model.named_steps["preprocess"]
        linear_model = model.named_steps["logistic_regression"]
        X_encoded = preprocessor.transform(sample)
        explainer = shap.LinearExplainer(linear_model, X_encoded)
        shap_values = explainer.shap_values(X_encoded)
        feature_names = list(preprocessor.get_feature_names_out())
    else:
        raise ValueError(f"no SHAP explainer configured for model type: {model_type!r}")

    reason_codes = []
    for i, row_index in enumerate(sample.index):
        contributions = sorted(
            zip(feature_names, shap_values[i], strict=True),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:top_n]
        reason_codes.append(
            {
                "row_index": int(row_index),
                "contributions": [
                    {"feature": name, "shap_value": float(value)} for name, value in contributions
                ],
            }
        )
    return reason_codes
