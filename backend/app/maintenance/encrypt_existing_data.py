"""One-off backfill of existing plaintext sensitive fields and local files.

Run from backend/. Take a verified backup first. The command is deliberately
opt-in for physical files because large storage roots can take a long time to scan.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.compliance_case import ComplianceCase
from app.models.customer_address import CustomerAddress
from app.models.customer_audit_log import CustomerAuditLog
from app.models.document import CustomerDocument
from app.models.document_extraction import DocumentExtraction
from app.models.file import File
from app.models.ocr_result import OCRResult
from app.storages.local_storage import LocalStorage

BATCH_SIZE = 250
PREFIX = "fpenc:v1:%"
MODELS_AND_FIELDS: tuple[tuple[Any, tuple[str, ...]], ...] = (
    (
        CustomerAddress,
        ("address_line_1", "address_line_2", "city", "state", "country", "postal_code"),
    ),
    (
        DocumentExtraction,
        (
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "nationality",
            "document_number",
            "expiry_date",
            "address",
        ),
    ),
    (OCRResult, ("extracted_text",)),
    (ComplianceCase, ("description", "resolution_reason")),
    (CustomerDocument, ("file_name",)),
    (File, ("original_filename",)),
    (CustomerAuditLog, ("old_value", "new_value")),
)


def _legacy_predicate(model: Any, fields: tuple[str, ...]) -> Any:
    predicates = []
    for name in fields:
        column = getattr(model, name)
        predicates.append(column.is_not(None) & cast(column, Text).not_like(PREFIX))
    return or_(*predicates)


def _count_legacy(session: Session, model: Any, fields: tuple[str, ...]) -> int:
    statement = (
        select(func.count()).select_from(model).where(_legacy_predicate(model, fields))
    )
    return int(session.scalar(statement) or 0)


def backfill_model(
    session: Session, model: Any, fields: tuple[str, ...], dry_run: bool
) -> int:
    count = _count_legacy(session, model, fields)
    print(f"{model.__name__}: {count} row(s) with plaintext values")
    if dry_run:
        return count

    changed = 0
    while True:
        ids = list(
            session.scalars(
                select(getattr(model, "id"))
                .where(_legacy_predicate(model, fields))
                .limit(BATCH_SIZE)
            ).all()
        )
        if not ids:
            break
        records = list(
            session.scalars(select(model).where(getattr(model, "id").in_(ids))).all()
        )
        for record in records:
            for name in fields:
                if getattr(record, name, None) is not None:
                    # The row was selected using its raw stored value.
                    # Result processors return cleartext, so flagging
                    # the attribute forces encrypted rebinding.
                    flag_modified(record, name)
            changed += 1
        session.commit()
    print(f"{model.__name__}: encrypted {changed} row(s)")
    return changed


def backfill_files(dry_run: bool) -> int:
    storage = LocalStorage(settings.STORAGE_PATH)
    root = storage.base_path
    candidates = [p for p in root.rglob("*") if p.is_file()]
    legacy: list[Path] = []
    for path in candidates:
        with path.open("rb") as handle:
            is_encrypted = handle.read(len(storage.MAGIC)) == storage.MAGIC
        if not is_encrypted:
            legacy.append(path)
    print(f"Storage files: {len(legacy)} plaintext file(s) beneath {root}")
    if dry_run:
        return len(legacy)
    changed = 0
    for path in legacy:
        storage.encrypt_legacy_file(path)
        changed += 1
    print(f"Storage files: encrypted {changed} file(s)")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report counts without changing data"
    )
    parser.add_argument(
        "--include-files",
        action="store_true",
        help="Also encrypt plaintext files under STORAGE_PATH",
    )
    args = parser.parse_args()

    total = 0
    # This is an offline, administrator-invoked maintenance command, not a request
    # path. It explicitly enables the repository's reviewed unscoped maintenance mode.
    with SessionLocal() as session:
        session.info["allow_unscoped_tenant_operations"] = True
        for model, fields in MODELS_AND_FIELDS:
            total += backfill_model(session, model, fields, args.dry_run)
        session.rollback()

    if args.include_files:
        total += backfill_files(args.dry_run)
    print(f"Total candidate rows/files: {total}")


if __name__ == "__main__":
    main()
