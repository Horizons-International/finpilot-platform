from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_task_service
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.task import (
    TaskAssignRequest,
    TaskCommentCreate,
    TaskCommentResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task_service import TaskService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import TaskPriority, TaskStatus, UserRole

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["Tasks"],
)


@router.post(
    "",
    response_model=APIResponse[TaskResponse],
)
def create_task(
    payload: TaskCreate,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
):
    task = task_service.create_task(
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task created successfully.",
        data=task,
    )


@router.get(
    "",
    response_model=APIResponse[TaskListResponse],
)
def list_tasks(
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    assigned_to: UUID | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
):
    result = task_service.list_tasks(
        user_id=UUID(current_user["sub"]),
        role=UserRole(current_user["role"]),
        assigned_to=assigned_to,
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return APIResponse(
        success=True,
        message="Tasks retrieved successfully.",
        data=result,
    )


@router.get(
    "/my",
    response_model=APIResponse[TaskListResponse],
)
def list_my_tasks(
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
):
    user_id = UUID(current_user["sub"])

    result = task_service.list_tasks(
        user_id=user_id,
        role=UserRole(current_user["role"]),
        assigned_to=user_id,
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return APIResponse(
        success=True,
        message="Your tasks retrieved successfully.",
        data=result,
    )


@router.get(
    "/{task_id}",
    response_model=APIResponse[TaskDetailResponse],
)
def get_task(
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
):
    task = task_service.get_task_detail(
        task_id,
        user_id=UUID(current_user["sub"]),
        role=UserRole(current_user["role"]),
    )

    return APIResponse(
        success=True,
        message="Task retrieved successfully.",
        data=task,
    )


@router.put(
    "/{task_id}",
    response_model=APIResponse[TaskResponse],
)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
):
    task = task_service.update_task(
        task_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task updated successfully.",
        data=task,
    )


@router.post(
    "/{task_id}/assign",
    response_model=APIResponse[TaskResponse],
)
def assign_task(
    task_id: UUID,
    payload: TaskAssignRequest,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR, UserRole.COMPLIANCE_OFFICER, resource_type="task"
        )
    ),
):
    task = task_service.assign_task(
        task_id,
        payload.assigned_to,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task assigned successfully.",
        data=task,
    )


@router.patch(
    "/{task_id}/status",
    response_model=APIResponse[TaskResponse],
)
def update_task_status(
    task_id: UUID,
    payload: TaskStatusUpdate,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
):
    task = task_service.update_status(
        task_id,
        payload.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task status updated successfully.",
        data=task,
    )


@router.post(
    "/{task_id}/complete",
    response_model=APIResponse[TaskResponse],
)
def complete_task(
    task_id: UUID,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
):
    task = task_service.complete_task(
        task_id,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task completed successfully.",
        data=task,
    )


@router.post(
    "/{task_id}/comments",
    response_model=APIResponse[TaskCommentResponse],
)
def add_comment(
    task_id: UUID,
    payload: TaskCommentCreate,
    request: Request,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
):
    comment = task_service.add_comment(
        task_id,
        payload,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return APIResponse(
        success=True,
        message="Task comment added successfully.",
        data=comment,
    )


@router.get(
    "/{task_id}/comments",
    response_model=APIResponse[list[TaskCommentResponse]],
)
def get_comments(
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
):
    comments = task_service.get_comments(
        task_id,
        user_id=UUID(current_user["sub"]),
        role=UserRole(current_user["role"]),
    )

    return APIResponse(
        success=True,
        message="Task comments retrieved successfully.",
        data=comments,
    )
