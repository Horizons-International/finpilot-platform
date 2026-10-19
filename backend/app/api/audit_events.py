"""Compliance-authorized, tenant-scoped audit-event search."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.audit_event import AuditEventListResponse, AuditEventResponse
from app.services.audit_event_service import AuditEventService
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/audit-events", tags=["Audit Events"])
_AUDIT_READ_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.AUDITOR,
)


@router.get("", response_model=APIResponse[AuditEventListResponse])
def search_audit_events(
    action: str | None = Query(default=None, max_length=100),
    entity_type: str | None = Query(default=None, max_length=100),
    entity_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(
        require_roles(*_AUDIT_READ_ROLES, resource_type="audit_events")
    ),
    db: Session = Depends(get_db),
) -> APIResponse[AuditEventListResponse]:
    try:
        tenant_raw = current_user.get("tenant_id")
        if not tenant_raw:
            raise HTTPException(status_code=403, detail="Tenant context is required")
        tenant_id = UUID(str(tenant_raw))
        service = AuditEventService(db, tenant_id)
        events, total = service.search(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
            page=page,
            page_size=page_size,
        )
        body = AuditEventListResponse(
            events=[AuditEventResponse.model_validate(event) for event in events],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )
        return APIResponse(
            success=True,
            message="Audit events retrieved successfully.",
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
