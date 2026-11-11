"""Request-test-aware AsyncSession context for ASGI middleware."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_async_db


@asynccontextmanager
async def middleware_async_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Open an async session, honoring FastAPI's async DB override in tests."""
    overrides = getattr(request.app, "dependency_overrides", {})
    override_factory = overrides.get(get_async_db)
    if override_factory is not None:
        provided: Any = override_factory()
        if inspect.isasyncgen(provided):
            generator = cast(AsyncGenerator[AsyncSession, None], provided)
            session = await anext(generator)
            try:
                yield session
            finally:
                await generator.aclose()
            return
        if inspect.isawaitable(provided):
            provided = await provided
        if isinstance(provided, AsyncSession):
            try:
                yield provided
            finally:
                await provided.close()
            return
        if hasattr(provided, "__aenter__") and hasattr(provided, "__aexit__"):
            async with provided as session:
                yield cast(AsyncSession, session)
            return
        raise TypeError("The get_async_db override did not provide an AsyncSession.")

    async with AsyncSessionLocal() as session:
        yield session
