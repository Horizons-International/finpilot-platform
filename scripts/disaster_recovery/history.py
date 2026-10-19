"""Append-only local backup/verification/restore history and a small CLI viewer."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HISTORY_NAME = "history.jsonl"


def append_history(
    output_root: Path, *, event: str, status: str, **details: Any
) -> Path:
    """Append one history record. Secrets and payloads must never be passed here."""
    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    history_path = root / HISTORY_NAME
    record = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "event": event,
        "status": status,
        **{
            key: str(value) if isinstance(value, Path) else value
            for key, value in details.items()
        },
    }
    with history_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        stream.flush()
    return history_path


def read_history(
    output_root: Path, *, limit: int = 50, event: str | None = None
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    path = output_root.expanduser().resolve() / HISTORY_NAME
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid history JSON on line {line_number}: {exc}"
                ) from exc
            if event is None or record.get("event") == event:
                records.append(record)
    return records[-limit:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / "finpilot-backups",
        help="Backup output root (default: ~/finpilot-backups)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Number of latest matching records to show",
    )
    parser.add_argument(
        "--event",
        choices=("backup", "verify", "restore-test"),
        help="Filter by event type",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print JSON instead of a readable table"
    )
    args = parser.parse_args()
    try:
        records = read_history(args.output_root, limit=args.limit, event=args.event)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(records, indent=2))
        return 0
    if not records:
        history_path = args.output_root.expanduser().resolve() / HISTORY_NAME
        print(f"No backup history found at {history_path}")
        return 0
    print(f"History: {args.output_root.expanduser().resolve() / HISTORY_NAME}")
    for record in records:
        timestamp = record.get("timestamp_utc", "unknown-time")
        event = record.get("event", "unknown-event")
        status = record.get("status", "unknown-status").upper()
        bundle = record.get("bundle_dir", "")
        details = record.get("details", "")
        print(f"{timestamp} | {event:<12} | {status:<7} | {bundle} {details}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
