"""Credit Risk replay requests: real held-out applicants, packaged as `/predict/credit` payloads.

The serving API takes an applicant's own historical rows with each request (ADR-0009), so a
replayed request has to carry them too. This module slices them out of the raw Home Credit tables
for a chronologically spaced sample of the test split and writes one JSON request per line. The
generic sender in `bankml.monitoring.replay` posts them; nothing here talks to the API.

Runs once on `docker-01`, where the raw data lives (ADR-0014). The history tables are read in
chunks and filtered by applicant, because the full files do not fit in that VM's memory. The
output is derived from the raw data, so it is uploaded to the private `replay` blob container,
never committed (ADR-0016).
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from bankml.features.credit.anchor import compute_application_dates
from bankml.features.credit.pipeline import BASE_APPLICANT_COLUMNS, load_config
from bankml.splitting import TEST, chronological_split

DOMAIN = "credit"
DEFAULT_SAMPLE_SIZE = 5000
_CHUNK_ROWS = 200_000

# History tables keyed by applicant. bureau_balance is keyed by SK_ID_BUREAU instead and is
# filtered through the bureau rows already selected.
_APPLICANT_TABLES = [
    "bureau",
    "previous_application",
    "POS_CASH_balance",
    "installments_payments",
    "credit_card_balance",
]


def select_replay_applicants(application_dates: pd.Series, split_config: dict, n: int) -> pd.Series:
    """`n` test-split applicants, evenly spaced through the test window in date order.

    Spaced rather than sampled at random: the replay walks forward through time the way real
    traffic would, and the same config always selects the same applicants.
    """
    frame = application_dates.rename("APPLICATION_DATE").to_frame()
    in_test = frame[chronological_split(frame, "APPLICATION_DATE", split_config) == TEST]
    ordered = in_test["APPLICATION_DATE"].sort_values(kind="stable")
    if n >= len(ordered):
        return ordered
    positions = np.unique(np.linspace(0, len(ordered) - 1, n).round().astype(int))
    return ordered.iloc[positions]


def _clean(value):
    """JSON-safe scalar: NaN becomes null, numpy scalars become Python ones."""
    if isinstance(value, float | np.floating) and math.isnan(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _read_filtered(path: Path, key: str, ids: set[int]) -> pd.DataFrame:
    parts = [chunk[chunk[key].isin(ids)] for chunk in pd.read_csv(path, chunksize=_CHUNK_ROWS)]
    return pd.concat(parts, ignore_index=True)


def build_requests(
    application_df: pd.DataFrame,
    history: dict[str, pd.DataFrame],
    selected: pd.Series,
) -> Iterator[dict]:
    """One request payload per selected applicant, in decision-date order.

    `decision_date` is the applicant's synthetic APPLICATION_DATE (ADR-0008), so the API's as-of
    aggregation sees exactly the window training saw for the same applicant.
    """
    applicants = application_df.set_index("SK_ID_CURR")
    grouped = {
        name: dict(tuple(df.groupby("SK_ID_CURR")))
        for name, df in history.items()
        if name != "bureau_balance"
    }
    balance_by_bureau = dict(tuple(history["bureau_balance"].groupby("SK_ID_BUREAU")))

    for applicant_id, decision_date in selected.items():
        row = applicants.loc[applicant_id, BASE_APPLICANT_COLUMNS]
        payload = {
            "applicant_id": int(applicant_id),
            "decision_date": pd.Timestamp(decision_date).isoformat(),
            "applicant": {k: _clean(v) for k, v in row.items()},
        }
        for name in _APPLICANT_TABLES:
            rows = grouped[name].get(applicant_id)
            payload[name] = [] if rows is None else _records(rows)
        bureau_ids = [r["SK_ID_BUREAU"] for r in payload["bureau"]]
        payload["bureau_balance"] = [
            record
            for bureau_id in bureau_ids
            if bureau_id in balance_by_bureau
            for record in _records(balance_by_bureau[bureau_id])
        ]
        yield payload


def build_replay_file(output: Path, n: int = DEFAULT_SAMPLE_SIZE) -> int:
    config = load_config()
    raw_dir = Path(os.environ["BANKML_DATA_ROOT"]) / config["raw_data"]["directory"]

    application_df = pd.read_csv(
        raw_dir / "application_train.csv", usecols=["SK_ID_CURR", *BASE_APPLICANT_COLUMNS]
    )
    anchor = config["synthetic_anchor"]
    dates = compute_application_dates(application_df, anchor["start"], anchor["end"])
    selected = select_replay_applicants(dates, config["split"], n)
    ids = set(selected.index)

    history = {
        name: _read_filtered(raw_dir / f"{name}.csv", "SK_ID_CURR", ids)
        for name in _APPLICANT_TABLES
    }
    bureau_ids = set(history["bureau"]["SK_ID_BUREAU"])
    history["bureau_balance"] = _read_filtered(
        raw_dir / "bureau_balance.csv", "SK_ID_BUREAU", bureau_ids
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(output, "wt") as f:
        for payload in build_requests(application_df, history, selected):
            f.write(json.dumps(payload) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--upload", action="store_true", help="also upload to the private replay blob container"
    )
    args = parser.parse_args()

    count = build_replay_file(args.output, args.n)
    print(f"Wrote {count} replay requests to {args.output}")
    if args.upload:
        from bankml.monitoring.replay import upload_requests

        blob = upload_requests(args.output, DOMAIN)
        print(f"Uploaded to {blob}")


if __name__ == "__main__":
    main()
