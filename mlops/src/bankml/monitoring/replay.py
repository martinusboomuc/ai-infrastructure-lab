"""Replay traffic: post prepared requests to the deployed API so its monitoring has data to judge.

The drift job needs at least `DEFAULT_MIN_CURRENT` logged predictions before PSI means anything,
and the API sees almost no real traffic. This sends a daily batch of held-out applicants, built
by a domain's own replay module (`bankml.features.credit.replay`), through the public prediction
endpoint (ADR-0016). Every replayed request carries `X-Traffic-Source: replay`, which the API
writes into the prediction log, so replayed and real traffic stay separable. It authenticates with
its own key, `BANKML_API_KEY`, which the API knows as the `replay` client (ADR-0017).

The request file and a cursor live in the private `replay` blob container. The cursor records
how far the replay has got, so a missed or repeated run neither skips nor resends applicants; at
the end of the file it wraps around to the start.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AZURE_CONTAINER = "replay"
TRAFFIC_SOURCE_HEADER = "X-Traffic-Source"
DEFAULT_BATCH_SIZE = 200
# A replay run fails when more than this share of its requests fail: a few transient errors are
# tolerated, a broken API or payload is not.
MAX_FAILURE_RATE = 0.1
_RETRIES = 2
_TIMEOUT_SECONDS = 60


def _requests_blob(domain: str) -> str:
    return f"{domain}/requests.jsonl.gz"


def _cursor_blob(domain: str) -> str:
    return f"{domain}/cursor.json"


def _container():
    from azure.storage.blob import ContainerClient

    container = ContainerClient.from_connection_string(
        os.environ["AZURE_STORAGE_CONNECTION_STRING"], container_name=AZURE_CONTAINER
    )
    if not container.exists():
        container.create_container()
    return container


def upload_requests(path: Path, domain: str) -> str:
    """Upload a built request file and reset the cursor, since positions in the old file no
    longer mean anything in the new one.
    """
    container = _container()
    with open(path, "rb") as f:
        container.upload_blob(_requests_blob(domain), f, overwrite=True)
    container.upload_blob(_cursor_blob(domain), json.dumps({"position": 0}), overwrite=True)
    return f"{AZURE_CONTAINER}/{_requests_blob(domain)}"


def load_requests(domain: str) -> list[str]:
    raw = _container().download_blob(_requests_blob(domain)).readall()
    return [line for line in gzip.decompress(raw).decode("utf-8").splitlines() if line.strip()]


def read_cursor(domain: str) -> int:
    from azure.core.exceptions import ResourceNotFoundError

    try:
        raw = _container().download_blob(_cursor_blob(domain)).readall()
    except ResourceNotFoundError:
        return 0
    return int(json.loads(raw)["position"])


def write_cursor(domain: str, position: int) -> None:
    _container().upload_blob(
        _cursor_blob(domain), json.dumps({"position": position}), overwrite=True
    )


def next_batch(lines: list[str], position: int, batch_size: int) -> tuple[list[str], int]:
    """The next `batch_size` requests from `position`, wrapping at the end of the file, and the
    position the following run starts from.
    """
    if not lines:
        return [], 0
    batch = [lines[(position + i) % len(lines)] for i in range(min(batch_size, len(lines)))]
    return batch, (position + len(batch)) % len(lines)


def post_request(api_url: str, endpoint: str, body: str, api_key: str) -> int:
    """POST one request, retrying connection errors and 5xx responses. Returns the final HTTP
    status, or 0 when the API could not be reached at all.
    """
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{endpoint}",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            TRAFFIC_SOURCE_HEADER: "replay",
        },
        method="POST",
    )
    status = 0
    for attempt in range(_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status < 500:
                return status
        except (urllib.error.URLError, TimeoutError):
            status = 0
        time.sleep(2**attempt)
    return status


def run_replay(
    domain: str, api_url: str, api_key: str, batch_size: int = DEFAULT_BATCH_SIZE
) -> dict:
    lines = load_requests(domain)
    position = read_cursor(domain)
    batch, next_position = next_batch(lines, position, batch_size)

    statuses: dict[int, int] = {}
    for body in batch:
        status = post_request(api_url, f"/predict/{domain}", body, api_key)
        statuses[status] = statuses.get(status, 0) + 1

    sent = statuses.get(200, 0)
    failed = len(batch) - sent
    # The cursor moves on even past failures: resending the same applicants would log them
    # twice, which skews drift more than a few missing ones do.
    write_cursor(domain, next_position)
    return {
        "domain": domain,
        "requested": len(batch),
        "sent": sent,
        "failed": failed,
        "statuses": {str(k): v for k, v in sorted(statuses.items())},
        "position": position,
        "next_position": next_position,
        "file_size": len(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()

    result = run_replay(
        args.domain, os.environ["BANKML_API_URL"], os.environ["BANKML_API_KEY"], args.batch_size
    )
    print(json.dumps(result, indent=2))
    if result["requested"] and result["failed"] / result["requested"] > MAX_FAILURE_RATE:
        sys.exit(1)


if __name__ == "__main__":
    main()
