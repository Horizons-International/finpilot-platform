"""Native-async API endpoints for enterprise implementation workspaces."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.async_security import get_async_current_user
from app.core.database import get_async_db
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.implementation_workspace import (
    ImplementationWorkspaceCommentCreate,
    ImplementationWorkspaceCommentListResponse,
    ImplementationWorkspaceCommentResponse,
    ImplementationWorkspaceCreate,
    ImplementationWorkspaceDetailResponse,
    ImplementationWorkspaceMemberCreate,
    ImplementationWorkspaceMemberResponse,
    ImplementationWorkspaceMilestoneCreate,
    ImplementationWorkspaceMilestoneResponse,
    ImplementationWorkspaceMilestoneUpdate,
    ImplementationWorkspaceResponse,
    ImplementationWorkspaceStageUpdate,
    ImplementationWorkspaceTaskCreate,
    ImplementationWorkspaceTaskResponse,
    ImplementationWorkspaceTaskUpdate,
    ImplementationWorkspaceUpdate,
)
from app.services.async_implementation_workspace_service import (
    AsyncImplementationWorkspaceService,
)

router = APIRouter(
    prefix="/api/v1/implementation-workspaces",
    tags=["Implementation Workspaces"],
)


def _service(db: AsyncSession) -> AsyncImplementationWorkspaceService:
    return AsyncImplementationWorkspaceService(db)


@router.post(
    "",
    response_model=APIResponse[ImplementationWorkspaceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an enterprise implementation workspace",
)
async def create_workspace(
    payload: ImplementationWorkspaceCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = await _service(db).create_workspace(payload, current_user)
    return APIResponse(
        success=True,
        message="Implementation workspace created successfully.",
        data=ImplementationWorkspaceResponse.model_validate(workspace),
    )


@router.get(
    "",
    response_model=APIResponse[list[ImplementationWorkspaceResponse]],
    summary="List workspaces shared with the current user",
)
async def list_workspaces(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[ImplementationWorkspaceResponse]]:
    workspaces = await _service(db).list_workspaces(current_user.id)
    return APIResponse(
        success=True,
        message="Implementation workspaces retrieved successfully.",
        data=[
            ImplementationWorkspaceResponse.model_validate(item) for item in workspaces
        ],
    )


@router.get(
    "/{workspace_id}",
    response_model=APIResponse[ImplementationWorkspaceDetailResponse],
    summary="Get workspace progress, milestones, tasks, and members",
)
async def get_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceDetailResponse]:
    workspace = await _service(db).get_workspace(workspace_id, current_user.id)
    return APIResponse(
        success=True,
        message="Implementation workspace retrieved successfully.",
        data=ImplementationWorkspaceDetailResponse.model_validate(workspace),
    )


@router.patch(
    "/{workspace_id}",
    response_model=APIResponse[ImplementationWorkspaceResponse],
    summary="Update timeline and implementation-area status",
)
async def update_workspace(
    workspace_id: UUID,
    payload: ImplementationWorkspaceUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = await _service(db).update_workspace(
        workspace_id, current_user.id, payload
    )
    return APIResponse(
        success=True,
        message="Implementation workspace updated successfully.",
        data=ImplementationWorkspaceResponse.model_validate(workspace),
    )


@router.patch(
    "/{workspace_id}/status",
    response_model=APIResponse[ImplementationWorkspaceResponse],
    summary="Advance the implementation workflow to the next stage",
)
async def update_workspace_stage(
    workspace_id: UUID,
    payload: ImplementationWorkspaceStageUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = await _service(db).update_stage(workspace_id, current_user.id, payload)
    return APIResponse(
        success=True,
        message="Implementation stage updated successfully.",
        data=ImplementationWorkspaceResponse.model_validate(workspace),
    )


@router.get(
    "/{workspace_id}/members",
    response_model=APIResponse[list[ImplementationWorkspaceMemberResponse]],
    summary="List internal and customer collaborators",
)
async def list_members(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[ImplementationWorkspaceMemberResponse]]:
    members = await _service(db).list_members(workspace_id, current_user.id)
    return APIResponse(
        success=True,
        message="Workspace members retrieved successfully.",
        data=[
            ImplementationWorkspaceMemberResponse.model_validate(item)
            for item in members
        ],
    )


@router.post(
    "/{workspace_id}/members",
    response_model=APIResponse[ImplementationWorkspaceMemberResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a collaborator from the internal or customer tenant",
)
async def add_member(
    workspace_id: UUID,
    payload: ImplementationWorkspaceMemberCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceMemberResponse]:
    member = await _service(db).add_member(workspace_id, current_user.id, payload)
    return APIResponse(
        success=True,
        message="Workspace member added successfully.",
        data=ImplementationWorkspaceMemberResponse.model_validate(member),
    )


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a collaborator from a workspace",
)
async def remove_member(
    workspace_id: UUID,
    member_user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> Response:
    await _service(db).remove_member(workspace_id, current_user.id, member_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/milestones",
    response_model=APIResponse[ImplementationWorkspaceMilestoneResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a dated implementation milestone",
)
async def create_milestone(
    workspace_id: UUID,
    payload: ImplementationWorkspaceMilestoneCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceMilestoneResponse]:
    milestone = await _service(db).create_milestone(
        workspace_id, current_user.id, payload
    )
    return APIResponse(
        success=True,
        message="Implementation milestone created successfully.",
        data=ImplementationWorkspaceMilestoneResponse.model_validate(milestone),
    )


@router.patch(
    "/{workspace_id}/milestones/{milestone_id}",
    response_model=APIResponse[ImplementationWorkspaceMilestoneResponse],
    summary="Update milestone owner, due date, or status",
)
async def update_milestone(
    workspace_id: UUID,
    milestone_id: UUID,
    payload: ImplementationWorkspaceMilestoneUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceMilestoneResponse]:
    milestone = await _service(db).update_milestone(
        workspace_id, milestone_id, current_user.id, payload
    )
    return APIResponse(
        success=True,
        message="Implementation milestone updated successfully.",
        data=ImplementationWorkspaceMilestoneResponse.model_validate(milestone),
    )


@router.get(
    "/{workspace_id}/tasks",
    response_model=APIResponse[list[ImplementationWorkspaceTaskResponse]],
    summary="List implementation tasks",
)
async def list_tasks(
    workspace_id: UUID,
    category: str | None = Query(
        default=None, pattern="^(PROJECT|TECHNICAL|BUSINESS)$"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[list[ImplementationWorkspaceTaskResponse]]:
    tasks = await _service(db).list_tasks(workspace_id, current_user.id)
    if category is not None:
        tasks = [task for task in tasks if task.category == category]
    return APIResponse(
        success=True,
        message="Implementation tasks retrieved successfully.",
        data=[
            ImplementationWorkspaceTaskResponse.model_validate(item) for item in tasks
        ],
    )


@router.post(
    "/{workspace_id}/tasks",
    response_model=APIResponse[ImplementationWorkspaceTaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create and optionally assign a project, technical, or business task",
)
async def create_task(
    workspace_id: UUID,
    payload: ImplementationWorkspaceTaskCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceTaskResponse]:
    task = await _service(db).create_task(workspace_id, current_user.id, payload)
    return APIResponse(
        success=True,
        message="Implementation task created successfully.",
        data=ImplementationWorkspaceTaskResponse.model_validate(task),
    )


@router.patch(
    "/{workspace_id}/tasks/{task_id}",
    response_model=APIResponse[ImplementationWorkspaceTaskResponse],
    summary="Assign a task or update its category, priority, or progress",
)
async def update_task(
    workspace_id: UUID,
    task_id: UUID,
    payload: ImplementationWorkspaceTaskUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceTaskResponse]:
    task = await _service(db).update_task(
        workspace_id, task_id, current_user.id, payload
    )
    return APIResponse(
        success=True,
        message="Implementation task updated successfully.",
        data=ImplementationWorkspaceTaskResponse.model_validate(task),
    )


@router.get(
    "/{workspace_id}/comments",
    response_model=APIResponse[ImplementationWorkspaceCommentListResponse],
    summary="List workspace or task collaboration comments",
)
async def list_comments(
    workspace_id: UUID,
    task_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceCommentListResponse]:
    comments = await _service(db).list_comments(workspace_id, current_user.id, task_id)
    return APIResponse(
        success=True,
        message="Workspace comments retrieved successfully.",
        data=ImplementationWorkspaceCommentListResponse(
            comments=[
                ImplementationWorkspaceCommentResponse.model_validate(item)
                for item in comments
            ],
            total=len(comments),
        ),
    )


@router.post(
    "/{workspace_id}/comments",
    response_model=APIResponse[ImplementationWorkspaceCommentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post a collaboration comment",
)
async def add_comment(
    workspace_id: UUID,
    payload: ImplementationWorkspaceCommentCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
) -> APIResponse[ImplementationWorkspaceCommentResponse]:
    comment = await _service(db).add_comment(workspace_id, current_user.id, payload)
    return APIResponse(
        success=True,
        message="Workspace comment added successfully.",
        data=ImplementationWorkspaceCommentResponse.model_validate(comment),
    )
