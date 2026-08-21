import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.api.users import router as users_router
from app.core.dependencies import get_current_user
from app.core.exceptions import (
    database_exception_handler,
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from app.core.logger import get_logger, setup_logging
from app.core.responses import APIResponse
from app.middleware.request_id import RequestIDMiddleware
from app.models.user import User
from app.schemas.auth import MeResponse

setup_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FinPilot API starting")

    yield

    logger.info("FinPilot API shutting down")


app = FastAPI(
    title="FinPilot API",
    lifespan=lifespan,
    description=(
        "FinPilot Platform API for user management, authentication, "
        "profiles, and administration."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profile_router)
app.include_router(files_router)
app.include_router(health_router)
app.add_exception_handler(
    HTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    SQLAlchemyError,
    database_exception_handler,
)

app.add_exception_handler(
    Exception,
    unexpected_exception_handler,
)


@app.get(
    "/health",
    tags=["Health"],
    summary="Check API health",
    description="Returns the current health status of the API.",
)
def health():
    return APIResponse(
        success=True,
        message="Service is healthy.",
        data={"status": "healthy"},
    )


@app.get(
    "/api/v1/me",
    response_model=APIResponse[MeResponse],
    tags=["Users"],
    summary="Get current user",
    description="Returns the profile information of the currently authenticated user.",
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return APIResponse(
        success=True,
        message="User profile retrieved successfully.",
        data=MeResponse(
            id=str(current_user.id),
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            email=current_user.email,
            role=current_user.role,
        ),
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        elapsed_time = (time.perf_counter() - start_time) * 1000

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        logger.info(
            "Request ID=%s | %s %s | %s | %.2fms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_time,
        )

        return response

    except Exception:
        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        logger.exception(
            "Request ID=%s | %s %s | unexpected error",
            request_id,
            request.method,
            request.url.path,
        )

        raise
