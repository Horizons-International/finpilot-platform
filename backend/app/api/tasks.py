from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.async_security import require_async_roles
from app.core.database import get_async_db
from app.core.responses import APIResponse
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
from app.services.async_service_bridge import run_sync_in_tenant
from app.services.task_service import TaskService
from app.utils.constants import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from app.utils.enums import TaskPriority, TaskStatus, UserRole

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


def _metadata(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


async def _task_operation(
    db: AsyncSession,
    current_user: dict[str, Any],
    operation: Callable[[TaskService], Any],
) -> Any:
    tenant_id = UUID(current_user["tenant_id"])

    def invoke(sync_db: Session):
        service = TaskService(sync_db, tenant_id=tenant_id)
        return operation(service)

    return await run_sync_in_tenant(db, tenant_id, invoke)


@router.post("", response_model=APIResponse[TaskResponse])
async def create_task(
    payload: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskResponse]:
    ip_address, user_agent = _metadata(request)
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskResponse.model_validate(
            service.create_task(
                payload,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(success=True, message="Task created successfully.", data=task)


@router.get("", response_model=APIResponse[TaskListResponse])
async def list_tasks(
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    assigned_to: UUID | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskListResponse]:
    result = await _task_operation(
        db,
        current_user,
        lambda service: service.list_tasks(
            user_id=UUID(current_user["sub"]),
            role=UserRole(current_user["role"]),
            assigned_to=assigned_to,
            status=status,
            priority=priority,
            page=page,
            page_size=page_size,
        ),
    )
    return APIResponse(
        success=True, message="Tasks retrieved successfully.", data=result
    )


@router.get("/my", response_model=APIResponse[TaskListResponse])
async def list_my_tasks(
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskListResponse]:
    user_id = UUID(current_user["sub"])
    result = await _task_operation(
        db,
        current_user,
        lambda service: service.list_tasks(
            user_id=user_id,
            role=UserRole(current_user["role"]),
            assigned_to=user_id,
            status=status,
            priority=priority,
            page=page,
            page_size=page_size,
        ),
    )
    return APIResponse(
        success=True, message="Your tasks retrieved successfully.", data=result
    )


@router.get("/{task_id}", response_model=APIResponse[TaskDetailResponse])
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskDetailResponse]:
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskDetailResponse.model_validate(
            service.get_task_detail(
                task_id,
                user_id=UUID(current_user["sub"]),
                role=UserRole(current_user["role"]),
            )
        ),
    )
    return APIResponse(success=True, message="Task retrieved successfully.", data=task)


@router.put("/{task_id}", response_model=APIResponse[TaskResponse])
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskResponse]:
    ip_address, user_agent = _metadata(request)
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskResponse.model_validate(
            service.update_task(
                task_id,
                payload,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(success=True, message="Task updated successfully.", data=task)


@router.post("/{task_id}/assign", response_model=APIResponse[TaskResponse])
async def assign_task(
    task_id: UUID,
    payload: TaskAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskResponse]:
    ip_address, user_agent = _metadata(request)
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskResponse.model_validate(
            service.assign_task(
                task_id,
                payload.assigned_to,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(success=True, message="Task assigned successfully.", data=task)


@router.patch("/{task_id}/status", response_model=APIResponse[TaskResponse])
async def update_task_status(
    task_id: UUID,
    payload: TaskStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskResponse]:
    ip_address, user_agent = _metadata(request)
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskResponse.model_validate(
            service.update_status(
                task_id,
                payload.status,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(
        success=True, message="Task status updated successfully.", data=task
    )


@router.post("/{task_id}/complete", response_model=APIResponse[TaskResponse])
async def complete_task(
    task_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskResponse]:
    ip_address, user_agent = _metadata(request)
    task = await _task_operation(
        db,
        current_user,
        lambda service: TaskResponse.model_validate(
            service.complete_task(
                task_id,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(success=True, message="Task completed successfully.", data=task)


@router.post("/{task_id}/comments", response_model=APIResponse[TaskCommentResponse])
async def add_comment(
    task_id: UUID,
    payload: TaskCommentCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="task",
        )
    ),
) -> APIResponse[TaskCommentResponse]:
    ip_address, user_agent = _metadata(request)
    comment = await _task_operation(
        db,
        current_user,
        lambda service: TaskCommentResponse.model_validate(
            service.add_comment(
                task_id,
                payload,
                user_id=UUID(current_user["sub"]),
                email=current_user["email"],
                role=UserRole(current_user["role"]),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        ),
    )
    return APIResponse(
        success=True, message="Task comment added successfully.", data=comment
    )


@router.get(
    "/{task_id}/comments", response_model=APIResponse[list[TaskCommentResponse]]
)
async def get_comments(
    task_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict[str, Any] = Depends(
        require_async_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            UserRole.AUDITOR,
            resource_type="task",
        )
    ),
) -> APIResponse[list[TaskCommentResponse]]:
    comments = await _task_operation(
        db,
        current_user,
        lambda service: [
            TaskCommentResponse.model_validate(item)
            for item in service.get_comments(
                task_id,
                user_id=UUID(current_user["sub"]),
                role=UserRole(current_user["role"]),
            )
        ],
    )
    return APIResponse(
        success=True, message="Task comments retrieved successfully.", data=comments
    )
