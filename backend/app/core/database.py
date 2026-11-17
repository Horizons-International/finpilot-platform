"""Synchronous and asynchronous SQLAlchemy engines and session factories."""

from collections.abc import AsyncGenerator, Generator
from typing import Any, Literal

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_pool_echo: bool | Literal["debug"] = (
    "debug" if settings.DATABASE_POOL_LOGGING else False
)
_database_connect_args = {
    "application_name": settings.DATABASE_APPLICATION_NAME,
}

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    echo_pool=_pool_echo,
    pool_size=settings.DATABASE_SYNC_POOL_SIZE,
    max_overflow=settings.DATABASE_SYNC_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
    connect_args=_database_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    echo_pool=_pool_echo,
    pool_size=settings.DATABASE_ASYNC_POOL_SIZE,
    max_overflow=settings.DATABASE_ASYNC_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
    connect_args=_database_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


def get_database_pool_status() -> dict[str, dict[str, int]]:
    """Return pool counters for this process (not a cluster-wide aggregate).

    The async engine exposes its underlying synchronous pool facade through
    ``sync_engine``. Both pool implementations provide the QueuePool counters
    used below. Calling this function does not acquire a database connection.
    """

    def snapshot(
        pool: Any, *, configured_size: int, max_overflow: int
    ) -> dict[str, int]:
        return {
            "configured_size": configured_size,
            "max_overflow": max_overflow,
            "max_capacity": configured_size + max_overflow,
            "checked_in": int(pool.checkedin()),
            "checked_out": int(pool.checkedout()),
            # SQLAlchemy reports a negative value while the pool has not yet
            # opened its configured number of persistent connections.
            "current_overflow": int(pool.overflow()),
        }

    return {
        "sync": snapshot(
            engine.pool,
            configured_size=settings.DATABASE_SYNC_POOL_SIZE,
            max_overflow=settings.DATABASE_SYNC_MAX_OVERFLOW,
        ),
        "async": snapshot(
            async_engine.sync_engine.pool,
            configured_size=settings.DATABASE_ASYNC_POOL_SIZE,
            max_overflow=settings.DATABASE_ASYNC_MAX_OVERFLOW,
        ),
    }


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db
