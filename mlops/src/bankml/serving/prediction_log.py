"""Persisted prediction log (Phase 4) — one JSON line per served prediction.

This is the only durable record of a served prediction and its inputs. Phase 5's drift job and
delayed-label performance job (ROADMAP) read it back; what's written here has to be enough to
reconstruct both, which is why the full feature vector is included, not just the score.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def prediction_log_dir(domain: str) -> Path:
    override = os.environ.get("BANKML_PREDICTION_LOG_DIR")
    root = Path(override) if override else Path(os.environ["BANKML_DATA_ROOT"]) / "predictions"
    log_dir = root / domain
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def write_prediction_record(record: dict, domain: str = "credit") -> Path:
    """Append one JSON line to today's log file for `domain`. Returns the file written to."""
    log_dir = prediction_log_dir(domain)
    log_path = log_dir / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return log_path
