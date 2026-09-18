"""Auto-generated model card (roadmap item). Domain-agnostic (ADR-0002) — the domain name and
known-limitations language come from the caller/config, not hardcoded here.
"""

from __future__ import annotations


def generate_model_card(
    domain: str, role: str, model_type: str, metrics: dict, slice_metrics: dict
) -> str:
    lines = [
        f"# Model Card: {domain} — {role} ({model_type})",
        "",
        "## Metrics by split",
        "",
        "| Split | PR-AUC | ROC-AUC | Recall @ target FPR | Alert volume | Expected cost |",
        "|---|---|---|---|---|---|",
    ]
    for split_name, m in metrics.items():
        lines.append(
            f"| {split_name} | {m['pr_auc']:.4f} | {m['roc_auc']:.4f} | "
            f"{m['recall_at_target_fpr']:.4f} | {m['alert_volume_fraction']:.4f} | "
            f"{m['expected_cost']:.1f} |"
        )

    lines += ["", "## Slice metrics", ""]
    for split_name, slice_result in slice_metrics.items():
        lines.append(f"### {split_name}")
        for column, values in slice_result["slices"].items():
            for value, v in values.items():
                status = (
                    "N/A (single class)"
                    if v["within_tolerance"] is None
                    else ("pass" if v["within_tolerance"] else "FAIL")
                )
                pr_auc = "N/A" if v["pr_auc"] is None else f"{v['pr_auc']:.4f}"
                lines.append(f"- {column}={value!r} (n={v['n']}): PR-AUC={pr_auc} — {status}")

    lines += [
        "",
        "## Known limitations",
        "",
        "- Cost and slice-tolerance parameters are illustrative for a portfolio project, not a "
        "real bank's calibrated risk appetite.",
        "- Dates in this pipeline are synthetic (ADR-0008) — Home Credit's raw data carries no "
        "real application dates.",
        "- Reason codes are computed on a sample, not every prediction — see "
        "`src/bankml/evaluation/explain.py`.",
    ]
    return "\n".join(lines)
