"""Async persistence for cross-tenant implementation workspaces.

Every query that intentionally bypasses the active tenant filter is constrained by
an authenticated workspace-member predicate or by an already-authorized parent
workspace ID. Do not remove those predicates or the tenant-scope reasons.
"""

from __future__ import annotations

from typing import cast
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
from app.models.tenant import Tenant
from app.models.user import User


class AsyncImplementationWorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _unscoped(statement: Select, reason: str) -> Select:
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=reason,
        )

    async def tenant_exists(self, tenant_id: UUID) -> bool:
        statement = select(Tenant.id).where(Tenant.id == tenant_id)
        return (
            await self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Validate the customer tenant before creating an "
                        "implementation workspace."
                    ),
                )
            )
            is not None
        )

    async def get_user(self, user_id: UUID) -> User | None:
        statement = select(User).where(User.id == user_id, User.is_deleted.is_(False))
        return cast(
            User | None,
            await self.db.scalar(
                self._unscoped(
                    statement,
                    "Validate a proposed workspace collaborator by user ID.",
                )
            ),
        )

    async def get_member(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspaceMember | None:
        statement = select(ImplementationWorkspaceMember).where(
            ImplementationWorkspaceMember.workspace_id == workspace_id,
            ImplementationWorkspaceMember.user_id == user_id,
        )
        return cast(
            ImplementationWorkspaceMember | None,
            await self.db.scalar(
                self._unscoped(
                    statement,
                    "Check an authenticated user's membership in the exact workspace.",
                )
            ),
        )

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

    async def get_milestone(
        self, workspace_id: UUID, milestone_id: UUID
    ) -> ImplementationWorkspaceMilestone | None:
        statement = (
            select(ImplementationWorkspaceMilestone)
            .where(
                ImplementationWorkspaceMilestone.workspace_id == workspace_id,
                ImplementationWorkspaceMilestone.id == milestone_id,
            )
            .options(selectinload(ImplementationWorkspaceMilestone.assigned_user))
        )
        return cast(
            ImplementationWorkspaceMilestone | None,
            await self.db.scalar(
                self._unscoped(
                    statement,
                    "Retrieve a milestone only inside its authorized parent workspace.",
                )
            ),
        )

    async def get_task(
        self, workspace_id: UUID, task_id: UUID
    ) -> ImplementationWorkspaceTask | None:
        statement = (
            select(ImplementationWorkspaceTask)
            .where(
                ImplementationWorkspaceTask.workspace_id == workspace_id,
                ImplementationWorkspaceTask.id == task_id,
            )
            .options(selectinload(ImplementationWorkspaceTask.assigned_user))
        )
        return cast(
            ImplementationWorkspaceTask | None,
            await self.db.scalar(
                self._unscoped(
                    statement,
                    "Retrieve a task only inside its authorized parent workspace.",
                )
            ),
        )

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
                "List tasks only for a parent workspace authorized for the user.",
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
                (
                    "List comments only after verifying workspace membership "
                    "and task parentage."
                ),
            )
        )
        return list(result.all())
