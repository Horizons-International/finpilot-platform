from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_workflow_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.workflow import (
    WorkflowAdvanceRequest,
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
from app.services.workflow_service import WorkflowService
from app.utils.enums import UserRole, WorkflowStatus

router = APIRouter(
    prefix="/api/v1/workflows",
    tags=["Workflows"],
)


@router.post(
    "",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow",
    description="Create a configurable workflow definition.",
)
def create_workflow(
    payload: WorkflowCreate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowResponse]:
    workflow = service.create_workflow(
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    workflow.steps

    return APIResponse(
        success=True,
        message="Workflow created successfully.",
        data=WorkflowResponse.model_validate(
            workflow,
        ),
    )


@router.get(
    "",
    response_model=APIResponse[list[WorkflowResponse]],
    status_code=status.HTTP_200_OK,
    summary="List workflows",
    description="Retrieve configurable workflow definitions.",
)
def list_workflows(
    workflow_status: WorkflowStatus | None = Query(
        default=None,
        alias="status",
    ),
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[list[WorkflowResponse]]:
    workflows = service.list_workflows(
        status=workflow_status,
    )

    return APIResponse(
        success=True,
        message="Workflows retrieved successfully.",
        data=[WorkflowResponse.model_validate(workflow) for workflow in workflows],
    )


@router.get(
    "/executions/{execution_id}",
    response_model=APIResponse[WorkflowExecutionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get workflow execution",
    description="Retrieve the current state and step history of a workflow execution.",
)
def get_workflow_execution(
    execution_id: UUID,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    execution = service.get_execution(
        execution_id,
    )

    return APIResponse(
        success=True,
        message="Workflow execution retrieved successfully.",
        data=WorkflowExecutionResponse.model_validate(
            execution,
        ),
    )


@router.post(
    "/executions/{execution_id}/advance",
    response_model=APIResponse[WorkflowExecutionResponse],
    status_code=status.HTTP_200_OK,
    summary="Advance workflow execution",
    description="Complete the current workflow step and advance to the next step.",
)
def advance_workflow_execution(
    execution_id: UUID,
    payload: WorkflowAdvanceRequest,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    execution = service.advance_execution(
        execution_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        actor_role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow execution advanced successfully.",
        data=WorkflowExecutionResponse.model_validate(
            execution,
        ),
    )


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=APIResponse[WorkflowExecutionResponse],
    status_code=status.HTTP_200_OK,
    summary="Cancel workflow execution",
    description="Cancel an in-progress workflow execution.",
)
def cancel_workflow_execution(
    execution_id: UUID,
    payload: WorkflowExecutionCancelRequest,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    execution = service.cancel_execution(
        execution_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow execution cancelled successfully.",
        data=WorkflowExecutionResponse.model_validate(
            execution,
        ),
    )


@router.get(
    "/{workflow_id}",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Get workflow",
    description="Retrieve a workflow definition and its ordered steps.",
)
def get_workflow(
    workflow_id: UUID,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowResponse]:
    workflow = service.get_workflow(
        workflow_id,
    )

    return APIResponse(
        success=True,
        message="Workflow retrieved successfully.",
        data=WorkflowResponse.model_validate(
            workflow,
        ),
    )


@router.put(
    "/{workflow_id}",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Update workflow",
    description="Update a draft or inactive workflow definition.",
)
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowResponse]:
    workflow = service.update_workflow(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    workflow.steps

    return APIResponse(
        success=True,
        message="Workflow updated successfully.",
        data=WorkflowResponse.model_validate(
            workflow,
        ),
    )


@router.patch(
    "/{workflow_id}/status",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_200_OK,
    summary="Update workflow status",
    description="Activate or deactivate a workflow definition.",
)
def update_workflow_status(
    workflow_id: UUID,
    payload: WorkflowStatusUpdate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowResponse]:
    workflow = service.update_workflow_status(
        workflow_id,
        payload.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    workflow.steps

    return APIResponse(
        success=True,
        message="Workflow status updated successfully.",
        data=WorkflowResponse.model_validate(
            workflow,
        ),
    )


@router.post(
    "/{workflow_id}/steps",
    response_model=APIResponse[WorkflowStepResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add workflow step",
    description="Add an ordered step to a draft or inactive workflow.",
)
def add_workflow_step(
    workflow_id: UUID,
    payload: WorkflowStepCreate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowStepResponse]:
    step = service.add_step(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow step created successfully.",
        data=WorkflowStepResponse.model_validate(
            step,
        ),
    )


@router.put(
    "/{workflow_id}/steps/{step_id}",
    response_model=APIResponse[WorkflowStepResponse],
    status_code=status.HTTP_200_OK,
    summary="Update workflow step",
    description="Update a workflow step or change its order.",
)
def update_workflow_step(
    workflow_id: UUID,
    step_id: UUID,
    payload: WorkflowStepUpdate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[WorkflowStepResponse]:
    step = service.update_step(
        workflow_id,
        step_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow step updated successfully.",
        data=WorkflowStepResponse.model_validate(
            step,
        ),
    )


@router.delete(
    "/{workflow_id}/steps/{step_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete workflow step",
    description="Delete a workflow step from a draft or inactive workflow.",
)
def delete_workflow_step(
    workflow_id: UUID,
    step_id: UUID,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            resource_type="workflow",
        )
    ),
) -> APIResponse[None]:
    service.delete_step(
        workflow_id,
        step_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow step deleted successfully.",
        data=None,
    )


@router.post(
    "/{workflow_id}/executions",
    response_model=APIResponse[WorkflowExecutionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Start workflow execution",
    description="Start a new execution of an active workflow for a business entity.",
)
def start_workflow_execution(
    workflow_id: UUID,
    payload: WorkflowExecutionCreate,
    request: Request,
    service: WorkflowService = Depends(
        get_workflow_service,
    ),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="workflow_execution",
        )
    ),
) -> APIResponse[WorkflowExecutionResponse]:
    execution = service.start_execution(
        workflow_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Workflow execution started successfully.",
        data=WorkflowExecutionResponse.model_validate(
            execution,
        ),
    )
