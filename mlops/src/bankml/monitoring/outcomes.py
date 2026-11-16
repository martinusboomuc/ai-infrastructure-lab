"""The outcome feed for replayed applicants (ADR-0021).

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


def replayed_applicant_ids(request_lines: list[str]) -> set[int]:
    return {int(json.loads(line)["applicant_id"]) for line in request_lines}


def build_outcomes(features: pd.DataFrame, applicant_ids: set[int], config: dict) -> pd.DataFrame:
    """The known outcome of each replayed applicant, from the domain's processed feature set."""
    key, target = config["entity_key"], config["target"]
    known = features[features[key].isin(applicant_ids)].dropna(subset=[target])
    return pd.DataFrame(
        {"applicant_id": known[key].astype(int), "outcome": known[target].astype(int)}
    ).drop_duplicates("applicant_id")


def publish_outcomes(domain: str) -> int:
    config = load_domain_config(domain)
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features = pd.read_parquet(
        data_root / "processed" / domain / "features.parquet",
        columns=[config["entity_key"], config["target"]],
    )
    outcomes = build_outcomes(features, replayed_applicant_ids(load_requests(domain)), config)
    _container().upload_blob(
        _outcomes_blob(domain), outcomes.to_csv(index=False).encode("utf-8"), overwrite=True
    )
    return len(outcomes)


def load_outcomes(domain: str) -> pd.Series:
    """`applicant_id -> outcome` (1 = defaulted) for every replayed applicant."""
    raw = _container().download_blob(_outcomes_blob(domain)).readall()
    frame = pd.read_csv(io.BytesIO(raw))
    return frame.set_index("applicant_id")["outcome"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the replayed applicants' outcomes.")
    parser.add_argument("--domain", default="credit")
    args = parser.parse_args()
    n = publish_outcomes(args.domain)
    print(f"Published {n} outcomes to replay/{_outcomes_blob(args.domain)}")


if __name__ == "__main__":
    main()
