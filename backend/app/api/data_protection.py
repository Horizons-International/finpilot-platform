"""Compliance-admin endpoints for tenant-scoped protection controls."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, get_storage
from app.core.security import require_roles
from app.models.data_protection import DataLegalHold
from app.schemas.data_protection import (
    DataProtectionPolicyResponse,
    DeletionRequestCreate,
    DeletionRequestResponse,
    LegalHoldCreate,
    LegalHoldResponse,
    RetentionPolicyUpdate,
)
from app.services.data_protection_service import DataProtectionService
from app.storages.base_storage import BaseStorage
from app.utils.enums import UserRole

router = APIRouter(prefix="/api/v1/data-protection", tags=["Data Protection"])
ADMIN_ROLES = (UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER)
READ_ROLES = (*ADMIN_ROLES, UserRole.AUDITOR)


def _service(
    db: Session, current_user: dict[str, Any], storage: BaseStorage | None = None
) -> DataProtectionService:
    try:
        tenant_id = uuid.UUID(str(current_user["tenant_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=403, detail="Tenant context is required"
        ) from exc
    return DataProtectionService(db, tenant_id, storage)


@router.get("/policies", response_model=list[DataProtectionPolicyResponse])
def list_policies(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="data-protection")
    ),
) -> list[DataProtectionPolicyResponse]:
    policies = _service(db, current_user).repo.list_policies()
    return [DataProtectionPolicyResponse.model_validate(item) for item in policies]


@router.put("/policies/{resource_type}", response_model=DataProtectionPolicyResponse)
def update_policy(
    resource_type: str,
    payload: RetentionPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-policy")
    ),
) -> DataProtectionPolicyResponse:
    try:
        service = _service(db, current_user)
        policy = service.set_policy(
            resource_type,
            payload.retention_days,
            payload.enabled,
            payload.legal_basis,
            uuid.UUID(str(current_user["sub"])),
        )
        db.commit()
        return DataProtectionPolicyResponse.model_validate(policy)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/legal-holds", response_model=list[LegalHoldResponse])
def list_legal_holds(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="data-protection")
    ),
) -> list[LegalHoldResponse]:
    service = _service(db, current_user)
    tenant_id = service.tenant_id
    statement = select(DataLegalHold).where(DataLegalHold.tenant_id == tenant_id)
    if active_only:
        statement = statement.where(DataLegalHold.active.is_(True))
    holds = list(
        db.scalars(statement.order_by(DataLegalHold.created_at.desc()).limit(500)).all()
    )
    return [LegalHoldResponse.model_validate(item) for item in holds]


@router.post(
    "/legal-holds",
    response_model=LegalHoldResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_legal_hold(
    payload: LegalHoldCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-legal-hold")
    ),
) -> LegalHoldResponse:
    try:
        hold = _service(db, current_user).create_legal_hold(
            payload.resource_type,
            payload.resource_id,
            payload.reason,
            uuid.UUID(str(current_user["sub"])),
        )
        db.commit()
        return LegalHoldResponse.model_validate(hold)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/legal-holds/{hold_id}/release", response_model=LegalHoldResponse)
def release_legal_hold(
    hold_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-legal-hold")
    ),
) -> LegalHoldResponse:
    try:
        hold = _service(db, current_user).release_legal_hold(
            hold_id, uuid.UUID(str(current_user["sub"]))
        )
        db.commit()
        return LegalHoldResponse.model_validate(hold)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)
        ) from exc


@router.post(
    "/deletion-requests",
    response_model=DeletionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_deletion(
    payload: DeletionRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-deletion")
    ),
) -> DeletionRequestResponse:
    try:
        request = _service(db, current_user).request_deletion(
            payload.resource_type,
            payload.resource_id,
            payload.reason,
            uuid.UUID(str(current_user["sub"])),
        )
        db.commit()
        return DeletionRequestResponse.model_validate(request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/deletion-requests", response_model=list[DeletionRequestResponse])
def list_deletion_requests(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*READ_ROLES, resource_type="data-protection-deletion")
    ),
) -> list[DeletionRequestResponse]:
    requests = _service(db, current_user).repo.list_deletion_requests(limit=limit)
    return [DeletionRequestResponse.model_validate(item) for item in requests]


@router.post(
    "/deletion-requests/{request_id}/approve", response_model=DeletionRequestResponse
)
def approve_deletion(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-deletion")
    ),
) -> DeletionRequestResponse:
    try:
        request = _service(db, current_user).approve_deletion(
            request_id, uuid.UUID(str(current_user["sub"]))
        )
        db.commit()
        return DeletionRequestResponse.model_validate(request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/deletion-requests/{request_id}/execute", response_model=DeletionRequestResponse
)
def execute_deletion(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
    current_user: dict[str, Any] = Depends(
        require_roles(*ADMIN_ROLES, resource_type="data-protection-deletion")
    ),
) -> DeletionRequestResponse:
    try:
        service = _service(db, current_user, storage)
        request = service.execute_deletion(request_id)
        # execute_deletion commits its retry-safe intermediate and final states.
        return DeletionRequestResponse.model_validate(request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
