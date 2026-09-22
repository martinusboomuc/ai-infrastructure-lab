"""Persisted prediction log (Phase 4) — one JSON line per served prediction.

This is the only durable record of a served prediction and its inputs. Phase 5's drift job
(`monitoring/drift.py`) and delayed-label performance job (ROADMAP) read it back; what's written
here has to be enough to reconstruct both, which is why the full feature vector is included, not
just the score.

Two sinks, not one: a local JSON-lines file (always) and, when `AZURE_STORAGE_CONNECTION_STRING`
is set, an Azure Blob append blob too (best-effort — a logging failure must never fail a
prediction request that's already been scored). The local file alone is not durable on Azure
Container Apps: `BANKML_PREDICTION_LOG_DIR` there is a path inside the container's own
filesystem, baked into the Dockerfile, with no persistent volume mounted — every local-only
record is lost on restart, redeploy, or scale-to-zero. The Blob sink is what actually survives
that; found as a real gap while building Phase 5's drift job, which had no durable production
data to run against.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("bankml.serving.prediction_log")

AZURE_CONTAINER = "predictions"


def prediction_log_dir(domain: str) -> Path:
    override = os.environ.get("BANKML_PREDICTION_LOG_DIR")
    root = Path(override) if override else Path(os.environ["BANKML_DATA_ROOT"]) / "predictions"
    log_dir = root / domain
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _append_to_azure_blob(record: dict, domain: str) -> None:
    """Best-effort durable copy. Swallows every failure (network, auth, anything) rather than
    raising — the local write above has already succeeded by the time this runs, and a
    monitoring sink being briefly unreachable is not a reason to fail an already-scored
    prediction request.
    """
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        return

    from azure.storage.blob import BlobClient

    blob_name = f"{domain}/{datetime.now(UTC):%Y-%m-%d}.jsonl"
    try:
        client = BlobClient.from_connection_string(
            connection_string, container_name=AZURE_CONTAINER, blob_name=blob_name
        )
        if not client.exists():
            client.create_append_blob()
        client.append_block(json.dumps(record, default=str) + "\n")
    except Exception:
        logger.exception(
            "failed to append prediction record to Azure Blob (local copy still written)"
        )


def write_prediction_record(record: dict, domain: str = "credit") -> Path:
    """Append one JSON line to today's log file for `domain` — locally always, and to Azure Blob
    too when `AZURE_STORAGE_CONNECTION_STRING` is set. Returns the local file written to.
    """
    log_dir = prediction_log_dir(domain)
    log_path = log_dir / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    _append_to_azure_blob(record, domain)
    return log_path
