"""Helpers for binding service-layer database access to one tenant."""

from uuid import UUID

from sqlalchemy.orm import Session


def resolve_tenant_context(
    db: Session,
    tenant_id: UUID | None = None,
    *,
    resource_name: str = "tenant-owned data",
) -> UUID:
    """Resolve the trusted tenant ID and bind the SQLAlchemy session to it.

    An explicitly supplied tenant must agree with any tenant already bound to
    the session. A missing tenant is rejected instead of allowing an unscoped
    query or insert to proceed.
    """
    session_tenant = db.info.get("tenant_id")
    resolved = tenant_id if tenant_id is not None else session_tenant

    if not isinstance(resolved, UUID):
        raise ValueError(f"A tenant context is required for {resource_name}.")

    if session_tenant is not None and session_tenant != resolved:
        raise ValueError("The SQLAlchemy session is already bound to another tenant.")

    db.info["tenant_id"] = resolved
    return resolved
