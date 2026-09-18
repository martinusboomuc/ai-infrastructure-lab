"""Domain-agnostic chronological split and label maturity mechanism.

Per ADR-0004: no random splits, no random cross-validation. A domain's config drives this
purely mechanical implementation; how a domain produces the timestamp column this operates
on (real, or synthetic like Credit Risk's ADR-0008 anchor) is entirely that domain's concern,
not this module's. See ADR-0002: this file carries no domain-specific logic and must stay
reusable by any future domain unchanged.
"""

from __future__ import annotations

import pandas as pd

TRAIN = "train"
VALIDATION = "validation"
TEST = "test"
EXCLUDED = "excluded"


def chronological_split(df: pd.DataFrame, timestamp_col: str, split_config: dict) -> pd.Series:
    """Label each row train/validation/test/excluded from a domain's `split` config.

    `split_config` is expected in the shape documented in ARCHITECTURE.md and used by
    configs/credit.yaml: `{train: {from, to}, gap_days, validation: {from, to}, test: {from, to}}`.
    Rows outside every configured window (including the gap itself) are labelled "excluded".

    Raises ValueError if the configured gap between train and validation is narrower than
    `gap_days` claims — this is a config-consistency check, not a data check: it catches a
    boundary edited without updating the other, before it silently produces a leaking split.
    """
    train_from = pd.Timestamp(split_config["train"]["from"])
    train_to = pd.Timestamp(split_config["train"]["to"])
    validation_from = pd.Timestamp(split_config["validation"]["from"])
    validation_to = pd.Timestamp(split_config["validation"]["to"])
    test_from = pd.Timestamp(split_config["test"]["from"])
    test_to = pd.Timestamp(split_config["test"]["to"])
    gap_days = split_config["gap_days"]

    actual_gap_days = (validation_from - train_to).days
    if actual_gap_days < gap_days:
        raise ValueError(
            f"split config inconsistent: gap_days={gap_days} but train.to to "
            f"validation.from is only {actual_gap_days} days"
        )

    timestamps = df[timestamp_col]
    labels = pd.Series(EXCLUDED, index=df.index, dtype="object", name="split")
    labels[(timestamps >= train_from) & (timestamps <= train_to)] = TRAIN
    labels[(timestamps >= validation_from) & (timestamps <= validation_to)] = VALIDATION
    labels[(timestamps >= test_from) & (timestamps <= test_to)] = TEST
    return labels


def apply_label_maturity(
    df: pd.DataFrame, timestamp_col: str, maturity_days: int, as_of: pd.Timestamp
) -> pd.Series:
    """Mask rows whose label is mature enough to train on.

    A row is mature when `as_of - df[timestamp_col] >= maturity_days` (inclusive boundary: a
    row exactly `maturity_days` old counts as mature). Rows more recent than that are excluded
    — their outcome may not have had time to resolve yet (ADR-0004).
    """
    as_of = pd.Timestamp(as_of)
    age_days = (as_of - df[timestamp_col]).dt.days
    return age_days >= maturity_days
