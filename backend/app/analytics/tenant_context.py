"""Fail-closed tenant context helpers for analytics data access."""

from uuid import UUID

from sqlalchemy.orm import Session


def resolve_tenant_id(db: Session, tenant_id: UUID | None = None) -> UUID:
    """Resolve trusted tenant scope and bind it to the current session.

    Tenant-facing API requests should already have ``db.info['tenant_id']`` set
    by authentication. Background jobs may pass an explicit tenant ID. Conflicts
    are rejected to avoid reusing a session across tenant boundaries.
    """
    session_tenant = db.info.get("tenant_id")
    resolved = tenant_id if tenant_id is not None else session_tenant

    if not isinstance(resolved, UUID):
        raise ValueError("A tenant context is required for analytics data access.")

    if session_tenant is not None and session_tenant != resolved:
        raise ValueError("The SQLAlchemy session is already bound to another tenant.")

    db.info["tenant_id"] = resolved
    return resolved
