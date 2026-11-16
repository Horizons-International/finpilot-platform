"""Async read queries for cross-tenant implementation workspaces."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.models.implementation_workspace import (
    ImplementationWorkspace,
    ImplementationWorkspaceComment,
    ImplementationWorkspaceMember,
    ImplementationWorkspaceMilestone,
    ImplementationWorkspaceTask,
)


class AsyncImplementationWorkspaceReadRepository:
    """Read only workspace queries guarded by an explicit membership predicate.

    Workspace membership can span the implementation-owner and customer tenants.
    The reviewed tenant-filter bypasses below are therefore limited to queries
    that also constrain the exact workspace and/or authenticated member.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _unscoped(statement: Select, reason: str) -> Select:
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=reason,
        )

    async def list_for_user(self, user_id: UUID) -> list[ImplementationWorkspace]:
        statement = (
            select(ImplementationWorkspace)
            .join(
                ImplementationWorkspaceMember,
                ImplementationWorkspaceMember.workspace_id
                == ImplementationWorkspace.id,
            )
            .where(ImplementationWorkspaceMember.user_id == user_id)
            .options(selectinload(ImplementationWorkspace.tasks))
            .order_by(ImplementationWorkspace.updated_at.desc())
        )
        result = await self.db.scalars(
            self._unscoped(
                statement,
                "List workspaces with a membership row for the authenticated user.",
            )
        )
        return list(result.unique().all())

    async def get_for_member(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspace | None:
        statement = (
            select(ImplementationWorkspace)
            .join(
                ImplementationWorkspaceMember,
                ImplementationWorkspaceMember.workspace_id
                == ImplementationWorkspace.id,
            )
            .where(
                ImplementationWorkspace.id == workspace_id,
                ImplementationWorkspaceMember.user_id == user_id,
            )
            .options(
                selectinload(ImplementationWorkspace.tasks).selectinload(
                    ImplementationWorkspaceTask.assigned_user
                ),
                selectinload(ImplementationWorkspace.milestones).selectinload(
                    ImplementationWorkspaceMilestone.assigned_user
                ),
                selectinload(ImplementationWorkspace.members).selectinload(
                    ImplementationWorkspaceMember.user
                ),
            )
        )
        result = await self.db.scalars(
            self._unscoped(
                statement,
                "Load a workspace only when its authenticated membership matches.",
            )
        )
        return result.unique().first()

    async def list_members(
        self, workspace_id: UUID
    ) -> list[ImplementationWorkspaceMember]:
        statement = (
            select(ImplementationWorkspaceMember)
            .where(ImplementationWorkspaceMember.workspace_id == workspace_id)
            .options(selectinload(ImplementationWorkspaceMember.user))
            .order_by(ImplementationWorkspaceMember.created_at)
        )
        result = await self.db.scalars(
            self._unscoped(
                statement,
                "List members only after the parent workspace membership check.",
            )
        )
        return list(result.all())

    async def list_tasks(self, workspace_id: UUID) -> list[ImplementationWorkspaceTask]:
        statement = (
            select(ImplementationWorkspaceTask)
            .where(ImplementationWorkspaceTask.workspace_id == workspace_id)
            .options(selectinload(ImplementationWorkspaceTask.assigned_user))
            .order_by(ImplementationWorkspaceTask.created_at)
        )
        result = await self.db.scalars(
            self._unscoped(
                statement,
                "List tasks only for the parent workspace authorized for the user.",
            )
        )
        return list(result.all())

    async def list_comments(
        self, workspace_id: UUID, task_id: UUID | None = None
    ) -> list[ImplementationWorkspaceComment]:
        statement = select(ImplementationWorkspaceComment).where(
            ImplementationWorkspaceComment.workspace_id == workspace_id
        )
        if task_id is not None:
            statement = statement.where(
                ImplementationWorkspaceComment.task_id == task_id
            )
        statement = statement.options(
            selectinload(ImplementationWorkspaceComment.author)
        ).order_by(ImplementationWorkspaceComment.created_at)
        result = await self.db.scalars(
            self._unscoped(
                statement,
                "List comments only for the parent workspace authorized for the user.",
            )
        )
        return list(result.all())
