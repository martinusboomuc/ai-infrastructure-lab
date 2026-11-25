"""Test-bench examples (ADR-0025): real requests with outcomes, positives kept despite rarity."""

from __future__ import annotations

import json

import pandas as pd

from bankml.monitoring.examples import select_examples


def test_examples_mix_rare_positives_with_negatives_in_file_order():
    lines = [json.dumps({"transaction_id": f"t{i}", "transaction": {"amt": i}}) for i in range(100)]
    # One fraud in twenty, as rare cases are; t99 has no published outcome.
    outcomes = pd.Series({f"t{i}": int(i % 20 == 0) for i in range(99)})

    examples = select_examples(lines, outcomes, "transaction_id", count=10, positives=3)

    assert len(examples) == 10
    assert sum(e["outcome"] for e in examples) == 3
    assert [e["id"] for e in examples] == sorted(
        (e["id"] for e in examples), key=lambda i: int(i[1:])
    )
    assert examples[0]["request"]["transaction"]["amt"] == int(examples[0]["id"][1:])
    assert "t99" not in {e["id"] for e in examples}
