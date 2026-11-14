"""Async management endpoints for workflow task-assignment rules."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.task_assignment_rule import (
    TaskAssignmentRuleCreate,
    TaskAssignmentRuleResponse,
    TaskAssignmentRuleStatusUpdate,
    TaskAssignmentRuleUpdate,
)
from app.services.async_task_assignment_rule_service import (
    AsyncTaskAssignmentRuleService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/task-assignment-rules",
    tags=["Task Assignment Rules"],
)


@router.post("", response_model=APIResponse[TaskAssignmentRuleResponse])
async def create_assignment_rule(
    payload: TaskAssignmentRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
) -> APIResponse[TaskAssignmentRuleResponse]:
    rule = await AsyncTaskAssignmentRuleService(
        db, UUID(current_user["tenant_id"])
    ).create_rule(
        payload,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Task assignment rule created successfully.",
        data=TaskAssignmentRuleResponse.model_validate(rule),
    )


@router.get("", response_model=APIResponse[list[TaskAssignmentRuleResponse]])
async def list_assignment_rules(
    is_active: bool | None = Query(default=None),
    workflow_id: UUID | None = Query(default=None),
    workflow_step_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task_assignment_rule",
        )
    ),
) -> APIResponse[list[TaskAssignmentRuleResponse]]:
    rules = await AsyncTaskAssignmentRuleService(
        db, UUID(current_user["tenant_id"])
    ).list_rules(
        is_active=is_active,
        workflow_id=workflow_id,
        workflow_step_id=workflow_step_id,
    )
    return APIResponse(
        success=True,
        message="Task assignment rules retrieved successfully.",
        data=[TaskAssignmentRuleResponse.model_validate(rule) for rule in rules],
    )


@router.put("/{rule_id}", response_model=APIResponse[TaskAssignmentRuleResponse])
async def update_assignment_rule(
    rule_id: UUID,
    payload: TaskAssignmentRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
) -> APIResponse[TaskAssignmentRuleResponse]:
    rule = await AsyncTaskAssignmentRuleService(
        db, UUID(current_user["tenant_id"])
    ).update_rule(
        rule_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Task assignment rule updated successfully.",
        data=TaskAssignmentRuleResponse.model_validate(rule),
    )


@router.patch(
    "/{rule_id}/status",
    response_model=APIResponse[TaskAssignmentRuleResponse],
)
async def update_assignment_rule_status(
    rule_id: UUID,
    payload: TaskAssignmentRuleStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
) -> APIResponse[TaskAssignmentRuleResponse]:
    rule = await AsyncTaskAssignmentRuleService(
        db, UUID(current_user["tenant_id"])
    ).set_active(
        rule_id,
        payload.is_active,
        user_id=UUID(current_user["sub"]),
        email=str(current_user.get("email") or ""),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        message="Task assignment rule status updated successfully.",
        data=TaskAssignmentRuleResponse.model_validate(rule),
    )
