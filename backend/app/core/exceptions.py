import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.responses import APIResponse, ErrorDetail

logger = logging.getLogger(__name__)


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc

    logger.warning(
        "HTTP exception: %s %s - %s",
        request.method,
        request.url.path,
        exc.detail,
    )

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


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc

    logger.warning(
        "Validation error: %s %s",
        request.method,
        request.url.path,
    )

    errors: list[ErrorDetail] = []

    for error in exc.errors():
        location = error.get("loc", [])

        field_parts = [
            str(part)
            for part in location
            if part not in ("body", "query", "path", "header")
        ]

        field = ".".join(field_parts) if field_parts else None

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
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(),
    )


async def database_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, SQLAlchemyError):
        raise exc

    logger.exception(
        "Database error: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    response: APIResponse[None] = APIResponse(
        success=False,
        message="A database error occurred. Please try again later.",
        data=None,
        errors=None,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unexpected error: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    response: APIResponse[None] = APIResponse(
        success=False,
        message="An unexpected error occurred. Please try again later.",
        data=None,
        errors=None,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )
