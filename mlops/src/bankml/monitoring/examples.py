"""Examples for the Nexus test bench (ADR-0025): real held-out requests with their known outcome.

The test bench lets a person pick an applicant or a transaction, edit it, and send it to the
production model. Its examples are a small slice of the replay requests (ADR-0016, ADR-0023),
so they are real test-split cases the model never trained on, already in the API's request
shape. Each carries its outcome from the outcome feed, so the bench can show what actually
happened next to what the model says.

The slice is not representative on purpose: defaults and frauds are rare, so up to `positives` of
the examples are positive cases and the rest negative, each group evenly spaced through the
file. The bench is for trying cases, not for measuring the model; that is the performance job.

Runs on `docker-01` after the requests and outcomes are published, and writes
`<domain>/examples.json` to the private `replay` blob container.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable

import numpy as np
import pandas as pd

from bankml.monitoring.outcomes import load_domain_config, load_outcomes
from bankml.monitoring.replay import _container, load_requests

DEFAULT_COUNT = 50
DEFAULT_POSITIVES = 15


def _examples_blob(domain: str) -> str:
    return f"{domain}/examples.json"


def _spaced(items: list, n: int) -> list:
    if n >= len(items):
        return items
    positions = np.unique(np.linspace(0, len(items) - 1, n).round().astype(int))
    return [items[i] for i in positions]


def select_examples(
    lines: Iterable[str],
    outcomes: pd.Series,
    id_field: str,
    count: int = DEFAULT_COUNT,
    positives: int = DEFAULT_POSITIVES,
) -> list[dict]:
    """Up to `positives` positive and `count - positives` negative requests with known outcomes,
    each group evenly spaced, in file order."""
    # Positions and ids only: the Fraud file is too large to hold every parsed request.
    by_outcome: dict[int, list[tuple[int, str]]] = {0: [], 1: []}
    for position, line in enumerate(lines):
        entity = str(json.loads(line)[id_field])
        if entity in outcomes.index:
            by_outcome[int(outcomes[entity])].append((position, entity))

    chosen = _spaced(by_outcome[1], positives)
    chosen += _spaced(by_outcome[0], count - len(chosen))
    wanted = dict(sorted(chosen))
    return [
        {
            "id": wanted[position],
            "outcome": int(outcomes[wanted[position]]),
            "request": json.loads(line),
        }
        for position, line in enumerate(lines)
        if position in wanted
    ]


def publish_examples(domain: str, count: int, positives: int) -> int:
    field = load_domain_config(domain)["request_id_field"]
    examples = select_examples(
        load_requests(domain), load_outcomes(domain), field, count, positives
    )
    body = json.dumps({"domain": domain, "id_field": field, "examples": examples})
    _container().upload_blob(_examples_blob(domain), body.encode("utf-8"), overwrite=True)
    return len(examples)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish test-bench examples for a domain.")
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--positives", type=int, default=DEFAULT_POSITIVES)
    args = parser.parse_args()
    n = publish_examples(args.domain, args.count, args.positives)
    print(f"Published {n} examples to replay/{_examples_blob(args.domain)}")


if __name__ == "__main__":
    main()
