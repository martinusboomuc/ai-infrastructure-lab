"""The promotion gate that can actually block (roadmap item, exit criterion).

Evaluates the champion's test-split results only — the challenger runs through the same checks
purely for reporting (ADR-0005: "the comparison itself is a reported artifact"), never as
something that can be promoted instead of, or block, the champion. See the Phase 3 Stage 2 plan
for why: the champion is champion for an explainability reason, not a performance one, so a
challenger "beating" it isn't grounds for promotion.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_gate(
    test_metrics: dict,
    test_slice_metrics: dict,
    reason_codes: list[dict],
    model_card: str,
    config: dict,
) -> GateResult:
    reasons = []
    gate_config = config["evaluation"]["gate"]

    pr_auc = test_metrics["pr_auc"]
    if pr_auc < gate_config["min_pr_auc"]:
        reasons.append(
            f"PR-AUC {pr_auc:.4f} is below the configured floor {gate_config['min_pr_auc']}"
        )

    for column, values in test_slice_metrics["slices"].items():
        for value, v in values.items():
            if v["within_tolerance"] is False:
                reasons.append(f"slice {column}={value!r} exceeds its configured tolerance")

    if not reason_codes:
        reasons.append("no reason codes were produced")

    if not model_card or not model_card.strip():
        reasons.append("model card is missing or empty")

    return GateResult(passed=len(reasons) == 0, reasons=reasons)
