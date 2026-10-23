"""Persistence/query layer for implementation workspaces."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
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


class ImplementationWorkspaceRepository:
    """Queries are restricted by workspace membership and explicit parent IDs.

    The feature deliberately supports members from the implementation-owner and
    customer tenants. Such reads use a named tenant-filter bypass only after a
    workspace/user predicate is included; service methods enforce membership and
    same-workspace relationship validation before any mutation.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _unscoped(statement: Select, reason: str) -> Select:
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=reason,
        )

    def tenant_exists(self, tenant_id: UUID) -> bool:
        statement = select(Tenant.id).where(Tenant.id == tenant_id)
        return (
            self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Validate the customer tenant before "
                        "creating an implementation workspace."
                    ),
                )
            )
            is not None
        )

    def get_user(self, user_id: UUID) -> User | None:
        statement = select(User).where(User.id == user_id, User.is_deleted.is_(False))
        return cast(
            User | None,
            self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Validate a proposed implementation "
                        "workspace collaborator by user ID."
                    ),
                )
            ),
        )

    def get_member(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspaceMember | None:
        statement = select(ImplementationWorkspaceMember).where(
            ImplementationWorkspaceMember.workspace_id == workspace_id,
            ImplementationWorkspaceMember.user_id == user_id,
        )
        return cast(
            ImplementationWorkspaceMember | None,
            self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Check an authenticated user's membership in "
                        "the exact implementation workspace."
                    ),
                )
            ),
        )

    def list_for_user(self, user_id: UUID) -> list[ImplementationWorkspace]:
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
        return list(
            self.db.scalars(
                self._unscoped(
                    statement,
                    (
                        "List only implementation workspaces for which "
                        "the requesting user has a membership row."
                    ),
                )
            )
            .unique()
            .all()
        )

    def get_for_member(
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
        return cast(
            ImplementationWorkspace | None,
            self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Load one implementation workspace only when "
                        "its membership join matches the requester."
                    ),
                )
            ),
        )

    def list_members(self, workspace_id: UUID) -> list[ImplementationWorkspaceMember]:
        statement = (
            select(ImplementationWorkspaceMember)
            .where(ImplementationWorkspaceMember.workspace_id == workspace_id)
            .options(selectinload(ImplementationWorkspaceMember.user))
            .order_by(ImplementationWorkspaceMember.created_at)
        )
        return list(
            self.db.scalars(
                self._unscoped(
                    statement,
                    (
                        "List collaborators of a workspace after its "
                        "requester membership has been verified."
                    ),
                )
            ).all()
        )

    def get_milestone(
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
            self.db.scalar(
                self._unscoped(
                    statement,
                    (
                        "Retrieve a milestone using both its ID "
                        "and verified parent workspace ID."
                    ),
                )
            ),
        )

    def list_milestones(
        self, workspace_id: UUID
    ) -> list[ImplementationWorkspaceMilestone]:
        statement = (
            select(ImplementationWorkspaceMilestone)
            .where(ImplementationWorkspaceMilestone.workspace_id == workspace_id)
            .options(selectinload(ImplementationWorkspaceMilestone.assigned_user))
            .order_by(
                ImplementationWorkspaceMilestone.due_date,
                ImplementationWorkspaceMilestone.created_at,
            )
        )
        return list(
            self.db.scalars(
                self._unscoped(
                    statement,
                    "List milestones for the verified parent workspace only.",
                )
            ).all()
        )

    def get_task(
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
            self.db.scalar(
                self._unscoped(
                    statement,
                    "Retrieve a task by ID only inside the verified parent workspace.",
                )
            ),
        )

    def list_tasks(self, workspace_id: UUID) -> list[ImplementationWorkspaceTask]:
        statement = (
            select(ImplementationWorkspaceTask)
            .where(ImplementationWorkspaceTask.workspace_id == workspace_id)
            .options(selectinload(ImplementationWorkspaceTask.assigned_user))
            .order_by(ImplementationWorkspaceTask.created_at)
        )
        return list(
            self.db.scalars(
                self._unscoped(
                    statement,
                    "List tasks for the verified parent workspace only.",
                )
            ).all()
        )

    def list_comments(
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
        return list(
            self.db.scalars(
                self._unscoped(
                    statement,
                    (
                        "List collaboration comments after verifying workspace "
                        "membership and optional task parentage."
                    ),
                )
            ).all()
        )
