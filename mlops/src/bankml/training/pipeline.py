"""Champion/challenger training + evaluation orchestration.

Domain-agnostic (ADR-0002): which model type is champion/challenger comes entirely from a
domain's config (e.g. configs/credit.yaml's `modelling` section). This is the one place the
temporal-split discipline (fit only on train) and the fair-lending exclusion (never train on a
protected attribute) are enforced — individual model-fitting functions have no split or
column-sensitivity awareness of their own, by design.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import yaml

from bankml.evaluation.metrics import compute_metrics
from bankml.evaluation.slices import compute_slice_metrics
from bankml.training.gbm import fit_lightgbm
from bankml.training.scorecard import fit_scorecard

# Bookkeeping / identifier columns, and slice-only columns (fair-lending exclusion) — never
# passed to a model as a training feature.
NON_FEATURE_COLUMNS = {
    "SK_ID_CURR",
    "TARGET",
    "APPLICATION_DATE",
    "SPLIT",
    "IS_MATURE",
    "CODE_GENDER",
}


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def _prepare_features(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    X = df[feature_columns].copy()
    for column in X.select_dtypes(include=["object", "str"]).columns:
        X[column] = X[column].astype("category")
    return X


def train_and_evaluate(features_df: pd.DataFrame, config: dict) -> dict:
    """Fit champion and challenger per `config["modelling"]`, score every split, and return
    fitted models plus metrics/slice-metrics per role per split.

    An immature row's label isn't trustworthy for evaluation, not just training (ADR-0004), so
    every split here is drawn only from `IS_MATURE == True` rows.
    """
    mature = features_df[features_df["IS_MATURE"]].copy()
    feature_columns = _feature_columns(mature)
    categorical_columns = (
        mature[feature_columns].select_dtypes(include=["object", "str"]).columns.tolist()
    )

    splits = {
        name: mature[mature["SPLIT"] == name]
        for name in ("train", "validation", "test")
        if (mature["SPLIT"] == name).any()
    }
    train_df = splits["train"]
    X_train = _prepare_features(train_df, feature_columns)
    y_train = train_df["TARGET"]

    results: dict = {"models": {}, "metrics": {}, "slice_metrics": {}}

    for role in ("champion", "challenger"):
        model_type = config["modelling"][role]
        if model_type == "scorecard":
            model = fit_scorecard(X_train, y_train, categorical_variables=categorical_columns)
        elif model_type == "lightgbm":
            model = fit_lightgbm(X_train, y_train)
        else:
            raise ValueError(f"unknown model type in modelling config: {model_type!r}")

        results["models"][role] = model
        results["metrics"][role] = {}
        results["slice_metrics"][role] = {}

        for split_name, split_df in splits.items():
            X_split = _prepare_features(split_df, feature_columns)
            y_split = split_df["TARGET"]
            y_score = model.predict_proba(X_split)[:, 1]

            results["metrics"][role][split_name] = compute_metrics(
                y_split, y_score, config["evaluation"]
            )
            results["slice_metrics"][role][split_name] = compute_slice_metrics(
                split_df, y_split, y_score, config["evaluation"]
            )

    return results


def _print_report(results: dict, config: dict) -> None:
    for role in ("champion", "challenger"):
        model_type = config["modelling"][role]
        print(f"\n=== {role} ({model_type}) ===")
        for split_name, metrics in results["metrics"][role].items():
            print(
                f"  {split_name:>10}: PR-AUC={metrics['pr_auc']:.4f}  "
                f"ROC-AUC={metrics['roc_auc']:.4f}  "
                f"recall@FPR={metrics['recall_at_target_fpr']:.4f}  "
                f"alert_vol={metrics['alert_volume_fraction']:.4f}  "
                f"expected_cost={metrics['expected_cost']:.1f}"
            )
        for split_name, slice_result in results["slice_metrics"][role].items():
            for column, values in slice_result["slices"].items():
                flagged = [v for v, m in values.items() if m["within_tolerance"] is False]
                if flagged:
                    print(f"  {split_name:>10}: {column} outside tolerance for: {flagged}")


def main(domain: str = "credit") -> None:
    mlops_root = Path(__file__).resolve().parents[3]
    config_path = mlops_root / "configs" / f"{domain}.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features_path = data_root / "processed" / domain / "features.parquet"
    features_df = pd.read_parquet(features_path)

    results = train_and_evaluate(features_df, config)
    _print_report(results, config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="credit")
    args = parser.parse_args()
    main(domain=args.domain)
