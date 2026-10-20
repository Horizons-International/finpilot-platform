"""Read-only database query benchmark for FinPilot test/staging databases.

This intentionally benchmarks aggregate/report-like reads over existing tables.
It does not create, update, or delete rows. Still use a dedicated test database:
COUNT queries can scan a large table and consume substantial resources.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "performance" / "results"

# Queries are an explicit allowlist; no arbitrary SQL comes from command-line input.
QUERIES: dict[str, str] = {
    "customers_count": "SELECT count(*) FROM public.customers",
    "audit_logs_count": "SELECT count(*) FROM public.audit_logs",
    "customer_status_history_count": (
        "SELECT count(*) FROM public.customer_status_history"
    ),
    "customers_latest_100": (
        "SELECT id FROM public.customers ORDER BY created_at DESC LIMIT 100"
    ),
}


def _load_environment() -> None:
    """Load optional local development env files without printing secret values."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in (REPO_ROOT / "backend" / ".env", REPO_ROOT / "docker" / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def _safe_url_label(url: URL) -> str:
    """Return only the database host/name (never username, password, or query)."""
    host = url.host or "local"
    database = (url.database or "unknown").replace("/", "")
    return f"{host}/{database}"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    percentile_index = round((percentile / 100) * (len(ordered) - 1))
    index = max(0, min(len(ordered) - 1, percentile_index))
    return round(ordered[index], 3)


def run(args: argparse.Namespace) -> int:
    if not args.confirm_test_environment:
        print("Refusing to run without --confirm-test-environment.", file=sys.stderr)
        return 2

    _load_environment()
    raw_url = os.getenv("PERF_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not raw_url:
        print(
            "Set PERF_DATABASE_URL (preferred) or DATABASE_URL for the test database.",
            file=sys.stderr,
        )
        return 2

    try:
        parsed_url = make_url(raw_url)
        engine = create_engine(
            raw_url,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            connect_args={"connect_timeout": 5},
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"Could not create database engine: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "database": _safe_url_label(parsed_url),
        "iterations": args.iterations,
        "statement_timeout_ms": args.statement_timeout_ms,
        "queries": {},
        "warnings": [
            (
                "Read-only aggregate queries may still scan large tables and "
                "consume resources."
            ),
            (
                "This benchmark measures selected SQL statements, not end-to-end "
                "application latency."
            ),
        ],
    }
    failed = False
    try:
        with engine.connect() as connection:
            for query_name, sql in QUERIES.items():
                durations: list[float] = []
                error_message: str | None = None
                for _ in range(args.iterations):
                    try:
                        started = time.perf_counter()
                        with connection.begin():
                            connection.execute(text("SET TRANSACTION READ ONLY"))
                            connection.execute(
                                text(
                                    "SET LOCAL statement_timeout = "
                                    f"{int(args.statement_timeout_ms)}"
                                )
                            )
                            result = connection.execute(text(sql))
                            # Read one row for timing, not a full data export.
                            result.fetchone()
                        durations.append((time.perf_counter() - started) * 1000)
                    except SQLAlchemyError as exc:
                        first_line = str(exc).splitlines()[0][:200]
                        error_message = f"{type(exc).__name__}: {first_line}"
                        failed = True
                        break
                report["queries"][query_name] = {
                    "sql_label": query_name,
                    "samples": len(durations),
                    "mean_ms": (
                        round(statistics.mean(durations), 3) if durations else None
                    ),
                    "min_ms": round(min(durations), 3) if durations else None,
                    "max_ms": round(max(durations), 3) if durations else None,
                    "p50_ms": _percentile(durations, 50),
                    "p95_ms": _percentile(durations, 95),
                    "p99_ms": _percentile(durations, 99),
                    "error": error_message,
                }
    except SQLAlchemyError as exc:
        first_line = str(exc).splitlines()[0][:200]
        print(
            f"Database connection failed: {type(exc).__name__}: {first_line}",
            file=sys.stderr,
        )
        return 2
    finally:
        engine.dispose()

    report["finished_at"] = datetime.now(UTC).isoformat()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = (
        Path(args.output).resolve()
        if args.output
        else RESULTS_DIR
        / ("db-benchmark-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Database benchmark report: {target}")
    print(f"Database label: {report['database']}")
    for query_name, metrics in report["queries"].items():
        print(
            f"{query_name}: samples={metrics['samples']} "
            f"mean={metrics['mean_ms']}ms p95={metrics['p95_ms']}ms "
            f"max={metrics['max_ms']}ms error={metrics['error']}"
        )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-test-environment", action="store_true")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--statement-timeout-ms", type=int, default=15000)
    parser.add_argument("--output", help="Optional report JSON path")
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 100:
        parser.error("--iterations must be between 1 and 100")
    if args.statement_timeout_ms < 100 or args.statement_timeout_ms > 120000:
        parser.error("--statement-timeout-ms must be between 100 and 120000")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
