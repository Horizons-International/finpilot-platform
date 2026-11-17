from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_async_db, get_db
from app.core.logger import get_logger
from app.core.responses import APIResponse

router = APIRouter(
    tags=["Health"],
)

logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=APIResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check if the api endpoint is functional and ready to use.",
)
def health_check():
    return {
        "success": True,
        "message": "Application is healthy.",
        "data": {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        },
    }


def _check_sync_database(db: Session = Depends(get_db)) -> bool:
    """Check the synchronous pool in FastAPI's threadpool dependency context."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        logger.exception("Readiness check failed: synchronous database unavailable.")
        return False


def _not_ready_response() -> JSONResponse:
    response: APIResponse[dict[str, str]] = APIResponse(
        success=False,
        message="Application is not ready.",
        data={
            "status": "not_ready",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "unavailable",
        },
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description=(
        "Check that both synchronous and asynchronous SQLAlchemy database pools "
        "can execute a lightweight query."
    ),
)
async def readiness_check(
    sync_database_available: bool = Depends(_check_sync_database),
    async_db: AsyncSession = Depends(get_async_db),
):
    if not sync_database_available:
        return _not_ready_response()

    try:
        await async_db.execute(text("SELECT 1"))
        return APIResponse(
            success=True,
            message="Application is ready.",
            data={
                "status": "ready",
                "version": settings.APP_VERSION,
                "environment": settings.ENVIRONMENT,
                "database": "connected",
            },
        )
    except SQLAlchemyError:
        logger.exception("Readiness check failed: asynchronous database unavailable.")
        return _not_ready_response()
