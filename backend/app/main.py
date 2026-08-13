from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.users import router as users_router
from app.core.dependencies import get_current_user
from app.core.responses import APIResponse, ErrorDetail
from app.models.user import User
from app.schemas.auth import MeResponse

app = FastAPI(
    title="FinPilot API",
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profile_router)


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


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    response: APIResponse[None] = APIResponse(
        success=False,
        message=str(exc.detail),
        data=None,
        errors=None,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors: list[ErrorDetail] = []

    for error in exc.errors():
        location = error.get("loc", [])
        field = str(location[-1]) if location else None

        errors.append(
            ErrorDetail(
                field=field,
                message=error.get("msg", "Invalid value"),
            )
        )

    response: APIResponse[None] = APIResponse(
        success=False,
        message="Validation failed.",
        data=None,
        errors=errors,
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response.model_dump(),
    )
