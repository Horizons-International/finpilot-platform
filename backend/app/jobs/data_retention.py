"""Queue expired tenant records for approval; this command never deletes them."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.tenant import Tenant
from app.services.data_protection_service import DataProtectionService


def main() -> None:
    # Get the tenant IDs in a dedicated, explicitly unscoped maintenance session.
    with SessionLocal() as discovery:
        discovery.info["allow_unscoped_tenant_operations"] = True
        tenant_ids = list(discovery.scalars(select(Tenant.id)).all())

    total = 0
    for tenant_id in tenant_ids:
        with SessionLocal() as session:
            session.info["tenant_id"] = tenant_id
            service = DataProtectionService(session, tenant_id)
            queued = service.enqueue_expired_candidates()
            total += queued
            print(f"Tenant {tenant_id}: queued {queued} retention candidate(s)")
    print(f"Retention scan completed; {total} candidate(s) queued for human review")


if __name__ == "__main__":
    main()
