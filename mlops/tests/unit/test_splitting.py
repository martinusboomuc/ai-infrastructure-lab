import pandas as pd
import pytest

from bankml.splitting import (
    EXCLUDED,
    TEST,
    TRAIN,
    VALIDATION,
    apply_label_maturity,
    chronological_split,
)

SPLIT_CONFIG = {
    "train": {"from": "2016-01-01", "to": "2017-06-30"},
    "gap_days": 30,
    "validation": {"from": "2017-08-01", "to": "2017-12-31"},
    "test": {"from": "2018-01-01", "to": "2018-06-30"},
}


def _df(*dates):
    return pd.DataFrame({"ts": pd.to_datetime(list(dates))})


def test_labels_each_region_correctly():
    df = _df(
        "2016-06-15",  # inside train
        "2017-07-15",  # inside the gap (after train.to, before validation.from)
        "2017-09-15",  # inside validation
        "2018-03-15",  # inside test
        "2015-01-01",  # before everything
        "2018-12-31",  # after everything
    )
    labels = chronological_split(df, "ts", SPLIT_CONFIG)
    assert list(labels) == [TRAIN, EXCLUDED, VALIDATION, TEST, EXCLUDED, EXCLUDED]


def test_boundary_dates_are_inclusive():
    df = _df("2016-01-01", "2017-06-30", "2017-08-01", "2017-12-31", "2018-01-01", "2018-06-30")
    labels = chronological_split(df, "ts", SPLIT_CONFIG)
    assert list(labels) == [TRAIN, TRAIN, VALIDATION, VALIDATION, TEST, TEST]


def test_rejects_a_gap_narrower_than_configured():
    bad_config = {
        **SPLIT_CONFIG,
        "validation": {"from": "2017-07-15", "to": "2017-12-31"},  # only 15 days after train.to
    }
    df = _df("2016-06-15")
    with pytest.raises(ValueError, match="gap_days"):
        chronological_split(df, "ts", bad_config)


def test_label_maturity_boundary_is_inclusive():
    as_of = pd.Timestamp("2018-06-30")
    df = _df(
        "2017-01-06",  # exactly 540 days before as_of -> mature
        "2017-01-07",  # 539 days before as_of -> not yet mature
    )
    mask = apply_label_maturity(df, "ts", maturity_days=540, as_of=as_of)
    assert list(mask) == [True, False]
