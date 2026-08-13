from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType, AuditLog


def log_auth_event(
    db: Session,
    event_type: AuditEventType,
    user_id: UUID | None = None,
    email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    audit_log = AuditLog(
        user_id=user_id,
        email=email,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(audit_log)
    db.commit()
