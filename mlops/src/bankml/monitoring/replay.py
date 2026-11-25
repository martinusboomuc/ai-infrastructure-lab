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
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sized
from pathlib import Path
from typing import Protocol

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


class RequestLines(Sized, Protocol):
    def __iter__(self) -> Iterator[str]: ...


class RequestFile:
    """The downloaded request file, kept compressed and decompressed one line at a time.

    Decompressed, the Fraud file is about 420 MB (ADR-0023), more than the replay pod's memory;
    compressed it is about 75 MB. Each pass over it streams through gzip.
    """

    def __init__(self, compressed: bytes):
        self._compressed = compressed
        self._length: int | None = None

    def __iter__(self) -> Iterator[str]:
        with gzip.open(io.BytesIO(self._compressed), "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield line.rstrip("\n")

    def __len__(self) -> int:
        if self._length is None:
            self._length = sum(1 for _ in self)
        return self._length


def load_requests(domain: str) -> RequestFile:
    return RequestFile(_container().download_blob(_requests_blob(domain)).readall())


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


def next_batch(lines: RequestLines, position: int, batch_size: int) -> tuple[list[str], int]:
    """The next `batch_size` requests from `position`, wrapping at the end of the file, and the
    position the following run starts from. Reads `lines` in one pass, keeping only the batch.
    """
    total = len(lines)
    if not total:
        return [], 0
    order = [(position + i) % total for i in range(min(batch_size, total))]
    wanted = set(order)
    found = {i: line for i, line in enumerate(lines) if i in wanted}
    return [found[i] for i in order], (position + len(order)) % total


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
