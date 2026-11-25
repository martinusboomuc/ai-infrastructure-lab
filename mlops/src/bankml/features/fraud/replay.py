"""Fraud replay requests: real held-out transactions, packaged as `/predict/fraud` payloads.

Same role as `bankml.features.credit.replay` (ADR-0016): a request carries the card's own recent
transactions (ADR-0023), so a replayed request carries them too, sliced from the raw Sparkov files
for a chronologically spaced sample of the test split. The generic sender in
`bankml.monitoring.replay` posts them; nothing here talks to the API.

History is cut at `velocity.HISTORY_DAYS`, the longest look-back of any feature, and each history
row keeps only the five columns a feature reads. That keeps a request near 10 KB; the whole card
history would be about 2,200 rows.

Runs once on `docker-01`, where the raw data lives (ADR-0014). The output is derived from the raw
data, so it is uploaded to the private `replay` blob container, never committed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from bankml.features.fraud.pipeline import load_config
from bankml.features.fraud.velocity import HISTORY_DAYS
from bankml.splitting import TEST, chronological_split

DOMAIN = "fraud"
# 30 days of replay at 1,000 requests a day (ADR-0023): one performance window without reuse.
DEFAULT_SAMPLE_SIZE = 30_000

_TRANSACTION_COLUMNS = ["category", "amt", "lat", "long", "merch_lat", "merch_long"]
_HISTORY_COLUMNS = ["category", "amt", "merch_lat", "merch_long"]
_RAW_COLUMNS = ["trans_num", "trans_date_trans_time", "cc_num", *_TRANSACTION_COLUMNS]


def _timestamp(value: pd.Timestamp) -> str:
    return value.isoformat()


def select_replay_transactions(
    transactions: pd.DataFrame, split_config: dict, n: int
) -> pd.DataFrame:
    """`n` test-split transactions, evenly spaced through the test window in time order.

    Spaced rather than sampled at random, for the same reasons as Credit Risk: the replay walks
    forward through time, and the same config always selects the same transactions. Spacing also
    keeps the fraud rate the test split's own, which an alert rate or precision needs.
    """
    in_test = transactions[
        chronological_split(transactions, "trans_date_trans_time", split_config) == TEST
    ]
    ordered = in_test.sort_values("trans_date_trans_time", kind="stable")
    if n >= len(ordered):
        return ordered
    positions = np.unique(np.linspace(0, len(ordered) - 1, n).round().astype(int))
    return ordered.iloc[positions]


def build_requests(transactions: pd.DataFrame, selected: pd.DataFrame) -> Iterator[dict]:
    """One request payload per selected transaction, in time order.

    `transactions` holds every raw row the history may come from, with `trans_date_trans_time`
    already parsed. History is the card's transactions in `[t - HISTORY_DAYS, t)`, the same
    left-closed window `velocity.py` uses.
    """
    by_card = {
        card: group.sort_values("trans_date_trans_time", kind="stable")
        for card, group in transactions.groupby("cc_num")
    }
    window = pd.Timedelta(days=HISTORY_DAYS)

    for row in selected.itertuples(index=False):
        card = by_card[row.cc_num]
        times = card["trans_date_trans_time"].to_numpy()
        t = np.datetime64(row.trans_date_trans_time)
        start = np.searchsorted(times, t - window.to_timedelta64(), side="left")
        end = np.searchsorted(times, t, side="left")
        history = card.iloc[start:end]

        yield {
            "transaction_id": row.trans_num,
            "card_id": int(row.cc_num),
            "transaction": {
                "trans_date_trans_time": _timestamp(row.trans_date_trans_time),
                **{column: getattr(row, column) for column in _TRANSACTION_COLUMNS},
            },
            "history": [
                {
                    "trans_date_trans_time": _timestamp(h.trans_date_trans_time),
                    **{column: getattr(h, column) for column in _HISTORY_COLUMNS},
                }
                for h in history.itertuples(index=False)
            ],
        }


def load_transactions(config: dict) -> pd.DataFrame:
    raw_dir = Path(os.environ["BANKML_DATA_ROOT"]) / config["raw_data"]["directory"]
    frames = [
        pd.read_csv(raw_dir / filename, usecols=_RAW_COLUMNS)
        for filename in config["raw_data"]["tables"]
    ]
    transactions = pd.concat(frames, ignore_index=True)
    transactions["trans_date_trans_time"] = pd.to_datetime(transactions["trans_date_trans_time"])
    return transactions


def build_replay_file(output: Path, n: int = DEFAULT_SAMPLE_SIZE) -> int:
    config = load_config()
    transactions = load_transactions(config)
    selected = select_replay_transactions(transactions, config["split"], n)

    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(output, "wt") as f:
        for payload in build_requests(transactions, selected):
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
