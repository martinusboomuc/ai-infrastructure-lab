"""The outcome feed for replayed applicants and transactions (ADR-0021).

A bank learns whether a loan defaulted from its servicing system, months after the decision. This
project has no such system, but every replayed applicant is a real held-out Home Credit applicant
whose outcome is known. This module publishes those outcomes as a small table next to the replay
requests, in the private `replay` blob container, and reads it back for the performance job.

`publish_outcomes` runs once on `docker-01`, where the processed feature set lives (ADR-0014),
after the replay requests are built. The table holds only the replayed applicants' IDs and
outcomes, so the k3s job needs no copy of the feature set.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import yaml

from bankml.monitoring.replay import _container, load_requests

MLOPS_ROOT = Path(__file__).resolve().parents[3]


def load_domain_config(domain: str) -> dict:
    with open(MLOPS_ROOT / "configs" / f"{domain}.yaml") as f:
        return yaml.safe_load(f)


def _outcomes_blob(domain: str) -> str:
    return f"{domain}/outcomes.csv"


def replayed_ids(request_lines: Iterable[str], field: str) -> set[str]:
    """The entity ids in the replay requests, as strings: Credit Risk's are integers and Fraud's
    are hashes, and one type keeps the outcome table and its lookups the same for both."""
    return {str(json.loads(line)[field]) for line in request_lines}


def build_outcomes(features: pd.DataFrame, ids: set[str], config: dict) -> pd.DataFrame:
    """The known outcome of each replayed entity, from the domain's processed feature set."""
    key, target, field = config["entity_key"], config["target"], config["request_id_field"]
    keys = features[key].astype(str)
    known = features[keys.isin(ids)].dropna(subset=[target])
    return pd.DataFrame(
        {field: known[key].astype(str), "outcome": known[target].astype(int)}
    ).drop_duplicates(field)


def publish_outcomes(domain: str) -> int:
    config = load_domain_config(domain)
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features = pd.read_parquet(
        data_root / "processed" / domain / "features.parquet",
        columns=[config["entity_key"], config["target"]],
    )
    ids = replayed_ids(load_requests(domain), config["request_id_field"])
    outcomes = build_outcomes(features, ids, config)
    _container().upload_blob(
        _outcomes_blob(domain), outcomes.to_csv(index=False).encode("utf-8"), overwrite=True
    )
    return len(outcomes)


def load_outcomes(domain: str) -> pd.Series:
    """`id -> outcome` (1 = defaulted, or fraud) for every replayed entity, keyed by the id as a
    string."""
    field = load_domain_config(domain)["request_id_field"]
    raw = _container().download_blob(_outcomes_blob(domain)).readall()
    frame = pd.read_csv(io.BytesIO(raw), dtype={field: str})
    return frame.set_index(field)["outcome"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the replayed entities' outcomes.")
    parser.add_argument("--domain", default="credit")
    args = parser.parse_args()
    n = publish_outcomes(args.domain)
    print(f"Published {n} outcomes to replay/{_outcomes_blob(args.domain)}")


if __name__ == "__main__":
    main()
