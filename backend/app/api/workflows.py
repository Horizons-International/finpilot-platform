from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.schemas.workflow import (
    WorkflowAdvanceRequest,
    WorkflowAuditLogResponse,
    WorkflowCreate,
    WorkflowExecutionCancelRequest,
    WorkflowExecutionCreate,
    WorkflowExecutionResponse,
    WorkflowResponse,
    WorkflowStatusUpdate,
    WorkflowStepCreate,
    WorkflowStepResponse,
    WorkflowStepUpdate,
    WorkflowUpdate,
)
from app.services.async_workflow_service import AsyncWorkflowService
from app.utils.enums import UserRole, WorkflowStatus

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get(
        "user-agent"
    )


def _service(db: AsyncSession, current_user: dict[str, Any]) -> AsyncWorkflowService:
    db.info["tenant_user_id"] = UUID(current_user["sub"])
    db.info["tenant_user_email"] = current_user.get("email")
    return AsyncWorkflowService(db, UUID(current_user["tenant_id"]))


@router.post(
    "",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    payload: WorkflowCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[WorkflowResponse]:
    ip, agent = _metadata(request)
    workflow = await _service(db, current_user).create_workflow(
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow created successfully.",
        data=WorkflowResponse.model_validate(workflow),
    )


@router.get("", response_model=APIResponse[list[WorkflowResponse]])
async def list_workflows(
    workflow_status: WorkflowStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[list[WorkflowResponse]]:
    workflows = await _service(db, current_user).list_workflows(status=workflow_status)
    return APIResponse(
        success=True,
        message="Workflows retrieved successfully.",
        data=[WorkflowResponse.model_validate(item) for item in workflows],
    )


@router.get(
    "/executions/{execution_id}", response_model=APIResponse[WorkflowExecutionResponse]
)
async def get_workflow_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    execution = await _service(db, current_user).get_execution(execution_id)
    return APIResponse(
        success=True,
        message="Workflow execution retrieved successfully.",
        data=WorkflowExecutionResponse.model_validate(execution),
    )


@router.post(
    "/executions/{execution_id}/advance",
    response_model=APIResponse[WorkflowExecutionResponse],
)
async def advance_workflow_execution(
    execution_id: UUID,
    payload: WorkflowAdvanceRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    ip, agent = _metadata(request)
    execution = await _service(db, current_user).advance_execution(
        execution_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow execution advanced successfully.",
        data=WorkflowExecutionResponse.model_validate(execution),
    )


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=APIResponse[WorkflowExecutionResponse],
)
async def cancel_workflow_execution(
    execution_id: UUID,
    payload: WorkflowExecutionCancelRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    ip, agent = _metadata(request)
    execution = await _service(db, current_user).cancel_execution(
        execution_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow execution cancelled successfully.",
        data=WorkflowExecutionResponse.model_validate(execution),
    )


@router.get(
    "/executions/{execution_id}/audit-logs",
    response_model=APIResponse[list[WorkflowAuditLogResponse]],
)
async def get_workflow_audit_history(
    execution_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[list[WorkflowAuditLogResponse]]:
    history = await _service(db, current_user).get_audit_history(execution_id)
    return APIResponse(
        success=True,
        message="Workflow audit history retrieved successfully.",
        data=[WorkflowAuditLogResponse.model_validate(item) for item in history],
    )


@router.get("/{workflow_id}", response_model=APIResponse[WorkflowResponse])
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowResponse]:
    workflow = await _service(db, current_user).get_workflow(workflow_id)
    return APIResponse(
        success=True,
        message="Workflow retrieved successfully.",
        data=WorkflowResponse.model_validate(workflow),
    )


@router.put("/{workflow_id}", response_model=APIResponse[WorkflowResponse])
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[WorkflowResponse]:
    ip, agent = _metadata(request)
    workflow = await _service(db, current_user).update_workflow(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow updated successfully.",
        data=WorkflowResponse.model_validate(workflow),
    )


@router.patch("/{workflow_id}/status", response_model=APIResponse[WorkflowResponse])
async def update_workflow_status(
    workflow_id: UUID,
    payload: WorkflowStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[WorkflowResponse]:
    ip, agent = _metadata(request)
    workflow = await _service(db, current_user).update_workflow_status(
        workflow_id,
        payload.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow status updated successfully.",
        data=WorkflowResponse.model_validate(workflow),
    )


@router.post(
    "/{workflow_id}/steps",
    response_model=APIResponse[WorkflowStepResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_workflow_step(
    workflow_id: UUID,
    payload: WorkflowStepCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[WorkflowStepResponse]:
    ip, agent = _metadata(request)
    step = await _service(db, current_user).add_step(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow step created successfully.",
        data=WorkflowStepResponse.model_validate(step),
    )


@router.put(
    "/{workflow_id}/steps/{step_id}", response_model=APIResponse[WorkflowStepResponse]
)
async def update_workflow_step(
    workflow_id: UUID,
    step_id: UUID,
    payload: WorkflowStepUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[WorkflowStepResponse]:
    ip, agent = _metadata(request)
    step = await _service(db, current_user).update_step(
        workflow_id,
        step_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow step updated successfully.",
        data=WorkflowStepResponse.model_validate(step),
    )


@router.delete("/{workflow_id}/steps/{step_id}", response_model=APIResponse[None])
async def delete_workflow_step(
    workflow_id: UUID,
    step_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(UserRole.ADMINISTRATOR, resource_type="workflow")
    ),
) -> APIResponse[None]:
    ip, agent = _metadata(request)
    await _service(db, current_user).delete_step(
        workflow_id,
        step_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True, message="Workflow step deleted successfully.", data=None
    )


@router.post(
    "/{workflow_id}/executions",
    response_model=APIResponse[WorkflowExecutionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow_execution(
    workflow_id: UUID,
    payload: WorkflowExecutionCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    ip, agent = _metadata(request)
    execution = await _service(db, current_user).start_execution(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        ip_address=ip,
        user_agent=agent,
    )
    return APIResponse(
        success=True,
        message="Workflow execution started successfully.",
        data=WorkflowExecutionResponse.model_validate(execution),
    )
