"""Async read use cases for implementation workspaces."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.implementation_workspace import (
    ImplementationWorkspace,
    ImplementationWorkspaceComment,
    ImplementationWorkspaceMember,
    ImplementationWorkspaceTask,
)
from app.repositories.async_implementation_workspace_read_repository import (
    AsyncImplementationWorkspaceReadRepository,
)
from app.utils.errors import not_found


class AsyncImplementationWorkspaceReadService:
    """Expose workspace reads only after confirming the caller is a member."""

    def __init__(self, db: AsyncSession) -> None:
        self.repository = AsyncImplementationWorkspaceReadRepository(db)

    async def list_workspaces(self, user_id: UUID) -> list[ImplementationWorkspace]:
        return await self.repository.list_for_user(user_id)

    async def get_workspace(
        self, workspace_id: UUID, user_id: UUID
    ) -> ImplementationWorkspace:
        workspace = await self.repository.get_for_member(workspace_id, user_id)
        if workspace is None:
            # Do not disclose whether a non-member's workspace exists.
            raise not_found("Implementation workspace")
        return workspace

    async def list_members(
        self, workspace_id: UUID, user_id: UUID
    ) -> list[ImplementationWorkspaceMember]:
        await self.get_workspace(workspace_id, user_id)
        return await self.repository.list_members(workspace_id)

    async def list_tasks(
        self, workspace_id: UUID, user_id: UUID
    ) -> list[ImplementationWorkspaceTask]:
        await self.get_workspace(workspace_id, user_id)
        return await self.repository.list_tasks(workspace_id)

    async def list_comments(
        self, workspace_id: UUID, user_id: UUID, task_id: UUID | None = None
    ) -> list[ImplementationWorkspaceComment]:
        await self.get_workspace(workspace_id, user_id)
        return await self.repository.list_comments(workspace_id, task_id)
