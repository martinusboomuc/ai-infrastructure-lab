"""Delayed-label performance monitoring (Phase 5, ARCHITECTURE.md §7's "Delayed performance"
row: "Once labels mature, was the model actually right?").

Drift (`monitoring/drift.py`) answers "has the population or the model's own behavior moved" —
it never needs a true label, which is exactly why it can run immediately. This job answers the
harder, more direct question: for predictions old enough that their outcome would now be known,
was the *decision actually made* (the `decision` field logged at serving time — the model's
score compared against the threshold in effect then) correct against what actually happened?

A prediction only has a checkable outcome if two things are both true:

1. It's old enough. `configs/<domain>.yaml`'s `label.maturity_days` is the same window training
   uses to decide whether a *training* row's label can be trusted (ARCHITECTURE.md §3) — the
   identical logic applies to a served prediction's outcome.
2. The applicant is one we actually have a historical label for. This project's data is static
   (ARCHITECTURE.md's known simplifications — no live outcome-reporting pipeline exists), so
   "ground truth" here means matching `applicant_id` against `SK_ID_CURR` in the domain's own
   processed feature set, which carries Home Credit's original `TARGET` column. A served
   applicant with a synthetic or unmatched ID has no way to be checked — filtered out, not
   fabricated.

For BankML's own real logged predictions, both conditions being true at once is rare by design:
`maturity_days` is 540 (about 18 months) and most served requests use synthetic applicant IDs
for demonstration, not real historical ones. That is the honest current state, not a bug in this
job — a `no_labeled_matured_predictions` status is a real, meaningful result, not a failure.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score

from bankml.serving.prediction_log import read_all_records


def load_maturity_days(domain: str, mlops_root: Path) -> int:
    config_path = mlops_root / "configs" / f"{domain}.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["label"]["maturity_days"]


def load_ground_truth(domain: str) -> pd.Series:
    """`SK_ID_CURR -> TARGET` for every historically-labeled row in the domain's processed
    feature set (`training/pipeline.py` and `drift.py` both already treat this file as the
    domain's population of record). Only real, known outcomes — never a maturity-window
    approximation of one.
    """
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features_path = data_root / "processed" / domain / "features.parquet"
    df = pd.read_parquet(features_path, columns=["SK_ID_CURR", "TARGET"])
    df = df.dropna(subset=["TARGET"])
    return df.set_index("SK_ID_CURR")["TARGET"]


def compute_delayed_performance(
    domain: str, maturity_days: int, as_of: datetime | None = None
) -> dict[str, Any]:
    as_of = as_of or datetime.now(UTC)
    records = read_all_records(domain)

    matured = [
        r for r in records if (as_of - datetime.fromisoformat(r["timestamp"])).days >= maturity_days
    ]
    if not matured:
        return {
            "status": "no_matured_predictions",
            "domain": domain,
            "maturity_days": maturity_days,
            "n_logged": len(records),
        }

    ground_truth = load_ground_truth(domain)
    labeled = [r for r in matured if r["applicant_id"] in ground_truth.index]
    if not labeled:
        return {
            "status": "no_labeled_matured_predictions",
            "domain": domain,
            "maturity_days": maturity_days,
            "n_logged": len(records),
            "n_matured": len(matured),
        }

    y_true = pd.Series([ground_truth[r["applicant_id"]] for r in labeled])
    y_score = pd.Series([r["score"] for r in labeled])
    flagged = pd.Series([r["decision"] == "flag" for r in labeled])

    is_positive = y_true == 1
    true_positive = int((is_positive & flagged).sum())
    false_negative = int((is_positive & ~flagged).sum())
    false_positive = int((~is_positive & flagged).sum())
    true_negative = int((~is_positive & ~flagged).sum())

    result: dict[str, Any] = {
        "status": "ok",
        "domain": domain,
        "maturity_days": maturity_days,
        "n_logged": len(records),
        "n_matured": len(matured),
        "n_labeled": len(labeled),
        "accuracy": (true_positive + true_negative) / len(labeled),
        "precision": true_positive / (true_positive + false_positive)
        if (true_positive + false_positive) > 0
        else None,
        "recall": true_positive / (true_positive + false_negative)
        if (true_positive + false_negative) > 0
        else None,
        "true_positive": true_positive,
        "false_negative": false_negative,
        "false_positive": false_positive,
        "true_negative": true_negative,
    }

    # PR-AUC/ROC-AUC need both classes present — a handful of matured, labeled predictions can
    # easily be all-one-class, in which case sklearn raises rather than returning a degenerate
    # value. Reported when computable, omitted (not faked as 0.0 or 1.0) otherwise.
    if y_true.nunique() > 1:
        result["pr_auc"] = float(average_precision_score(y_true, y_score))
        result["roc_auc"] = float(roc_auc_score(y_true, y_score))

    return result


def log_delayed_performance_run(domain: str, result: dict[str, Any]) -> str:
    mlflow.set_experiment(f"{domain}-monitoring")
    with mlflow.start_run(run_name=f"{domain}-delayed-performance") as run:
        for key, value in result.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                mlflow.log_metric(key, value)
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "delayed_performance_report.json"
            report_path.write_text(json.dumps(result, indent=2, default=str))
            mlflow.log_artifact(str(report_path))
        return run.info.run_id


def main(domain: str = "credit", maturity_days: int | None = None) -> None:
    mlops_root = Path(__file__).resolve().parents[3]
    maturity_days = (
        maturity_days if maturity_days is not None else load_maturity_days(domain, mlops_root)
    )

    result = compute_delayed_performance(domain, maturity_days)
    print(json.dumps(result, indent=2, default=str))

    if result["status"] != "ok":
        return

    run_id = log_delayed_performance_run(domain, result)
    print(f"\nLogged delayed-performance run {run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="credit")
    parser.add_argument(
        "--maturity-days",
        type=int,
        default=None,
        help="Overrides the domain config's label.maturity_days — mainly for testing.",
    )
    args = parser.parse_args()
    main(domain=args.domain, maturity_days=args.maturity_days)
