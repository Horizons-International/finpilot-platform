import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.responses import APIResponse

router = APIRouter(
    tags=["Health"],
)

logger = logging.getLogger(__name__)


@router.get("/health")
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


@router.get("/ready")
def readiness_check(
    db: Session = Depends(get_db),
):
    try:
        db.execute(text("SELECT 1"))

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
        logger.exception("Readiness check failed: database unavailable.")

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
