from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_task_assignment_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.task_assignment_rule import (
    TaskAssignmentRuleCreate,
    TaskAssignmentRuleResponse,
    TaskAssignmentRuleStatusUpdate,
    TaskAssignmentRuleUpdate,
)
from app.services.task_assignment_service import (
    TaskAssignmentService,
)
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/task-assignment-rules",
    tags=["Task Assignment Rules"],
)


@router.post(
    "",
    response_model=APIResponse[TaskAssignmentRuleResponse],
)
def create_assignment_rule(
    payload: TaskAssignmentRuleCreate,
    request: Request,
    service: TaskAssignmentService = Depends(
        get_task_assignment_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
):
    rule = service.create_rule(
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return APIResponse(
        success=True,
        message="Task assignment rule created successfully.",
        data=rule,
    )


@router.get(
    "",
    response_model=APIResponse[list[TaskAssignmentRuleResponse]],
)
def list_assignment_rules(
    is_active: bool | None = Query(
        default=None,
    ),
    workflow_id: UUID | None = Query(
        default=None,
    ),
    workflow_step_id: UUID | None = Query(
        default=None,
    ),
    service: TaskAssignmentService = Depends(
        get_task_assignment_service,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task_assignment_rule",
        )
    ),
):
    rules = service.list_rules(
        is_active=is_active,
        workflow_id=workflow_id,
        workflow_step_id=workflow_step_id,
    )

    return APIResponse(
        success=True,
        message="Task assignment rules retrieved successfully.",
        data=rules,
    )


@router.put(
    "/{rule_id}",
    response_model=APIResponse[TaskAssignmentRuleResponse],
)
def update_assignment_rule(
    rule_id: UUID,
    payload: TaskAssignmentRuleUpdate,
    request: Request,
    service: TaskAssignmentService = Depends(
        get_task_assignment_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
):
    rule = service.update_rule(
        rule_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return APIResponse(
        success=True,
        message="Task assignment rule updated successfully.",
        data=rule,
    )


@router.patch(
    "/{rule_id}/status",
    response_model=APIResponse[TaskAssignmentRuleResponse],
)
def update_assignment_rule_status(
    rule_id: UUID,
    payload: TaskAssignmentRuleStatusUpdate,
    request: Request,
    service: TaskAssignmentService = Depends(
        get_task_assignment_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task_assignment_rule",
        )
    ),
):
    rule = service.set_active(
        rule_id,
        payload.is_active,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return APIResponse(
        success=True,
        message="Task assignment rule status updated successfully.",
        data=rule,
    )
