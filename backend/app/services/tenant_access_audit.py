from typing import NoReturn
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.audit_service import AuditService
from app.utils.errors import not_found


def deny_tenant_access(
    db: Session,
    *,
    resource_type: str,
    resource_id: UUID,
    resource_name: str,
    user_id: UUID | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> NoReturn:
    """Audit denied resource access, then return a generic 404."""

    user_id = user_id if user_id is not None else db.info.get("tenant_user_id")
    email = email if email is not None else db.info.get("tenant_user_email")
    ip_address = (
        ip_address if ip_address is not None else db.info.get("tenant_ip_address")
    )
    user_agent = (
        user_agent if user_agent is not None else db.info.get("tenant_user_agent")
    )

    db.rollback()

    AuditService(db).log_access_denied(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    db.commit()

    raise not_found(resource_name)
