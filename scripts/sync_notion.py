#!/usr/bin/env python3
"""Sync project state from the repository into Notion.

The repository is the source of truth. This script reads the roadmap and the
decision records, derives the current phase and progress, and writes them onto
a Notion project page. It never reads state back out of Notion, so there is no
possibility of a conflict.

Standard library only, so CI needs no install step.

Usage:
    python3 scripts/sync_notion.py --dry-run
    NOTION_TOKEN=secret_xxx python3 scripts/sync_notion.py

Environment:
    NOTION_TOKEN            Notion internal integration token (required unless --dry-run)
    NOTION_PROJECT_PAGE_ID  Target page in the Projects database (required unless --dry-run)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "mlops" / "ROADMAP.md"
DECISIONS = REPO_ROOT / "mlops" / "docs" / "decisions"

NOTION_API = "https://api.notion.com/v1/pages/{page_id}"
NOTION_VERSION = "2022-06-28"

PHASE_HEADER = re.compile(r"^##\s+(Phase\s+\d+\s+—\s+.+?)\s*(?:\*\(.*\)\*)?\s*$")
ANY_HEADER = re.compile(r"^##\s+")
CHECKED = re.compile(r"^\s*-\s*\[x\]", re.IGNORECASE)
UNCHECKED = re.compile(r"^\s*-\s*\[ \]")
ADR_FILE = re.compile(r"^\d{4}-.+\.md$")


class SyncError(RuntimeError):
    """Raised when the repository does not look the way this script expects."""


def parse_roadmap(path: Path) -> list[dict]:
    """Return one record per phase: title, done count, total count."""
    if not path.is_file():
        raise SyncError(f"Roadmap not found at {path}")

    phases: list[dict] = []
    current: dict | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        header = PHASE_HEADER.match(line)
        if header:
            current = {"title": header.group(1).strip(), "done": 0, "total": 0}
            phases.append(current)
            continue
        if ANY_HEADER.match(line):
            # A non-phase section such as "Later" ends the current phase.
            current = None
            continue
        if current is None:
            continue
        if CHECKED.match(line):
            current["done"] += 1
            current["total"] += 1
        elif UNCHECKED.match(line):
            current["total"] += 1

    if not phases:
        raise SyncError(
            f"No phase headers found in {path}. Expected lines like "
            '"## Phase 0 — Foundations".'
        )
    return phases


def count_adrs(directory: Path) -> int:
    if not directory.is_dir():
        raise SyncError(f"Decisions directory not found at {directory}")
    return sum(1 for f in directory.iterdir() if ADR_FILE.match(f.name))


def summarise(phases: list[dict], adrs: int) -> dict:
    """Pick the current phase and build the values written to Notion."""
    incomplete = [p for p in phases if p["total"] > p["done"]]
    current = incomplete[0] if incomplete else phases[-1]

    done_all = sum(p["done"] for p in phases)
    total_all = sum(p["total"] for p in phases)

    if incomplete:
        progress = (
            f"{current['done']}/{current['total']} in this phase"
            f" · {done_all}/{total_all} overall"
        )
    else:
        progress = f"All phases complete · {done_all}/{total_all}"

    return {
        "current_phase": current["title"],
        "progress": progress,
        "adrs": adrs,
        "synced": dt.date.today().isoformat(),
    }


def build_payload(summary: dict) -> dict:
    def text(value: str) -> dict:
        return {"rich_text": [{"type": "text", "text": {"content": value}}]}

    return {
        "properties": {
            "Current Phase": text(summary["current_phase"]),
            "Phase Progress": text(summary["progress"]),
            "Sync Source": text("mlops/ROADMAP.md"),
            "ADRs": {"number": summary["adrs"]},
            "Last Synced": {"date": {"start": summary["synced"]}},
        }
    }


def push(page_id: str, token: str, payload: dict) -> None:
    request = urllib.request.Request(
        NOTION_API.format(page_id=page_id),
        data=json.dumps(payload).encode("utf-8"),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SyncError(
            f"Notion rejected the update ({exc.code}). "
            f"Check that the integration is shared with the page. Response: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SyncError(f"Could not reach the Notion API: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the repository and print what would be sent, without calling Notion.",
    )
    args = parser.parse_args()

    try:
        phases = parse_roadmap(ROADMAP)
        summary = summarise(phases, count_adrs(DECISIONS))
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for phase in phases:
        print(f"  {phase['title']}: {phase['done']}/{phase['total']}")
    print()
    print(f"Current phase : {summary['current_phase']}")
    print(f"Progress      : {summary['progress']}")
    print(f"ADRs          : {summary['adrs']}")
    print(f"Last synced   : {summary['synced']}")

    if args.dry_run:
        print("\nDry run, nothing sent.")
        return 0

    token = os.environ.get("NOTION_TOKEN")
    page_id = os.environ.get("NOTION_PROJECT_PAGE_ID")
    missing = [n for n, v in (("NOTION_TOKEN", token), ("NOTION_PROJECT_PAGE_ID", page_id)) if not v]
    if missing:
        print(f"error: missing environment variable(s): {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        push(page_id, token, build_payload(summary))
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("\nNotion updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
