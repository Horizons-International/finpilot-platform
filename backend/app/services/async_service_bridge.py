"""Compatibility bridge for services not yet ported to AsyncSession.

The callback runs against the synchronous Session facade supplied by
AsyncSession.run_sync(). SQLAlchemy adapts ORM database I/O through the async
connection; callers must not perform blocking network/file I/O in the callback.
"""

from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_ResultT = TypeVar("_ResultT")


async def run_sync_in_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    operation: Callable[[Session], _ResultT],
) -> _ResultT:
    """Run a legacy ORM service operation using this request's async session."""

    if not isinstance(tenant_id, UUID):
        raise ValueError("A trusted tenant UUID is required.")

    def invoke(sync_db: Session) -> _ResultT:
        active_tenant_id = sync_db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError("The active database session belongs to another tenant.")
        sync_db.info["tenant_id"] = tenant_id
        return operation(sync_db)

    return await db.run_sync(invoke)
