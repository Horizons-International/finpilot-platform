from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.users import router as users_router
from app.core.dependencies import get_current_user
from app.core.exceptions import (
    database_exception_handler,
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from app.core.responses import APIResponse
from app.models.user import User
from app.schemas.auth import MeResponse

app = FastAPI(
    title="FinPilot API",
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profile_router)
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


@app.get("/health")
def health():
    return APIResponse(
        success=True,
        message="Service is healthy.",
        data={"status": "healthy"},
    )


@app.get("/api/v1/me", response_model=APIResponse[MeResponse])
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
