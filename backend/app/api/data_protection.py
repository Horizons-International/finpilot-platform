"""Tenant-scoped data-protection APIs.

Read-heavy list endpoints use AsyncSession. Policy/hold/deletion mutations remain
synchronous because they are short transactional workflows; physical deletion
also coordinates database commits with external storage cleanup.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.async_security import require_async_roles
from app.core.database import get_async_db, get_db
from app.core.dependencies import get_storage
from app.core.security import require_roles
from app.repositories.async_data_protection_read_repository import (
    AsyncDataProtectionReadRepository,
)
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


def _tenant_and_actor(current_user: dict[str, Any]) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        return (
            uuid.UUID(str(current_user["tenant_id"])),
            uuid.UUID(str(current_user["sub"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=403, detail="Tenant context is required"
        ) from exc


def _sync_service(
    db: Session, current_user: dict[str, Any], storage: BaseStorage | None = None
) -> DataProtectionService:
    tenant_id, _actor_id = _tenant_and_actor(current_user)
    return DataProtectionService(db, tenant_id, storage)


@router.get("/policies", response_model=list[DataProtectionPolicyResponse])
async def list_policies(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="data-protection")
    ),
) -> list[DataProtectionPolicyResponse]:
    tenant_id, _ = _tenant_and_actor(current_user)
    rows = await AsyncDataProtectionReadRepository(db, tenant_id).list_policies()
    return [DataProtectionPolicyResponse.model_validate(row) for row in rows]


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
        _tenant_id, actor_id = _tenant_and_actor(current_user)
        policy = _sync_service(db, current_user).set_policy(
            resource_type,
            payload.retention_days,
            payload.enabled,
            payload.legal_basis,
            actor_id,
        )
        db.commit()
        db.refresh(policy)
        return DataProtectionPolicyResponse.model_validate(policy)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/legal-holds", response_model=list[LegalHoldResponse])
async def list_legal_holds(
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="data-protection")
    ),
) -> list[LegalHoldResponse]:
    tenant_id, _ = _tenant_and_actor(current_user)
    rows = await AsyncDataProtectionReadRepository(db, tenant_id).list_legal_holds(
        active_only=active_only
    )
    return [LegalHoldResponse.model_validate(row) for row in rows]


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
        _tenant_id, actor_id = _tenant_and_actor(current_user)
        hold = _sync_service(db, current_user).create_legal_hold(
            payload.resource_type, payload.resource_id, payload.reason, actor_id
        )
        db.commit()
        db.refresh(hold)
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
        _tenant_id, actor_id = _tenant_and_actor(current_user)
        hold = _sync_service(db, current_user).release_legal_hold(hold_id, actor_id)
        db.commit()
        db.refresh(hold)
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
        _tenant_id, actor_id = _tenant_and_actor(current_user)
        item = _sync_service(db, current_user).request_deletion(
            payload.resource_type, payload.resource_id, payload.reason, actor_id
        )
        db.commit()
        db.refresh(item)
        return DeletionRequestResponse.model_validate(item)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/deletion-requests", response_model=list[DeletionRequestResponse])
async def list_deletion_requests(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(*READ_ROLES, resource_type="data-protection-deletion")
    ),
) -> list[DeletionRequestResponse]:
    tenant_id, _ = _tenant_and_actor(current_user)
    rows = await AsyncDataProtectionReadRepository(
        db, tenant_id
    ).list_deletion_requests(limit=limit)
    return [DeletionRequestResponse.model_validate(row) for row in rows]


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
        _tenant_id, actor_id = _tenant_and_actor(current_user)
        item = _sync_service(db, current_user).approve_deletion(request_id, actor_id)
        db.commit()
        db.refresh(item)
        return DeletionRequestResponse.model_validate(item)
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
        item = _sync_service(db, current_user, storage).execute_deletion(request_id)
        return DeletionRequestResponse.model_validate(item)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
