"""API endpoints for enterprise implementation workspaces."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import get_current_user
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
from app.services.implementation_workspace_service import ImplementationWorkspaceService

router = APIRouter(
    prefix="/api/v1/implementation-workspaces",
    tags=["Implementation Workspaces"],
)


def _service(db: Session) -> ImplementationWorkspaceService:
    return ImplementationWorkspaceService(db)


@router.post(
    "",
    response_model=APIResponse[ImplementationWorkspaceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create an enterprise implementation workspace",
)
def create_workspace(
    payload: ImplementationWorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = _service(db).create_workspace(payload, current_user)
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
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[ImplementationWorkspaceResponse]]:
    workspaces = _service(db).list_workspaces(current_user.id)
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
def get_workspace(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceDetailResponse]:
    workspace = _service(db).get_workspace(workspace_id, current_user.id)
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
def update_workspace(
    workspace_id: UUID,
    payload: ImplementationWorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = _service(db).update_workspace(workspace_id, current_user.id, payload)
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
def update_workspace_stage(
    workspace_id: UUID,
    payload: ImplementationWorkspaceStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceResponse]:
    workspace = _service(db).update_stage(workspace_id, current_user.id, payload)
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
def list_members(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[ImplementationWorkspaceMemberResponse]]:
    members = _service(db).list_members(workspace_id, current_user.id)
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
def add_member(
    workspace_id: UUID,
    payload: ImplementationWorkspaceMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceMemberResponse]:
    member = _service(db).add_member(workspace_id, current_user.id, payload)
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
def remove_member(
    workspace_id: UUID,
    member_user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _service(db).remove_member(workspace_id, current_user.id, member_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/milestones",
    response_model=APIResponse[ImplementationWorkspaceMilestoneResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a dated implementation milestone",
)
def create_milestone(
    workspace_id: UUID,
    payload: ImplementationWorkspaceMilestoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceMilestoneResponse]:
    milestone = _service(db).create_milestone(workspace_id, current_user.id, payload)
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
def update_milestone(
    workspace_id: UUID,
    milestone_id: UUID,
    payload: ImplementationWorkspaceMilestoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceMilestoneResponse]:
    milestone = _service(db).update_milestone(
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
def list_tasks(
    workspace_id: UUID,
    category: str | None = Query(
        default=None, pattern="^(PROJECT|TECHNICAL|BUSINESS)$"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[ImplementationWorkspaceTaskResponse]]:
    tasks = _service(db).list_tasks(workspace_id, current_user.id)
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
def create_task(
    workspace_id: UUID,
    payload: ImplementationWorkspaceTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceTaskResponse]:
    task = _service(db).create_task(workspace_id, current_user.id, payload)
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
def update_task(
    workspace_id: UUID,
    task_id: UUID,
    payload: ImplementationWorkspaceTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceTaskResponse]:
    task = _service(db).update_task(workspace_id, task_id, current_user.id, payload)
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
def list_comments(
    workspace_id: UUID,
    task_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceCommentListResponse]:
    comments = _service(db).list_comments(workspace_id, current_user.id, task_id)
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
def add_comment(
    workspace_id: UUID,
    payload: ImplementationWorkspaceCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> APIResponse[ImplementationWorkspaceCommentResponse]:
    comment = _service(db).add_comment(workspace_id, current_user.id, payload)
    return APIResponse(
        success=True,
        message="Workspace comment added successfully.",
        data=ImplementationWorkspaceCommentResponse.model_validate(comment),
    )
