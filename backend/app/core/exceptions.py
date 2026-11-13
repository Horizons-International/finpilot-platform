from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logger import get_logger
from app.core.responses import APIResponse, ErrorDetail
from app.middleware.async_session import middleware_async_session
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AuditEventType

logger = get_logger(__name__)


def _get_resource_context(
    request: Request,
) -> tuple[str, UUID | None]:
    resource_keys = (
        ("document_id", "document"),
        ("verification_case_id", "verification_case"),
        ("configuration_id", "system_configuration"),
        ("export_id", "report_export"),
        ("file_id", "file"),
        ("task_id", "task"),
        ("case_id", "case"),
        ("customer_id", "customer"),
    )

    for parameter, resource_type in resource_keys:
        value = request.path_params.get(parameter)

        if value is not None:
            try:
                return resource_type, UUID(str(value))
            except (TypeError, ValueError):
                return resource_type, None

    return "tenant_resource", None


def _uuid_or_none(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


async def _audit_resource_access_denied(request: Request) -> None:
    user_id = _uuid_or_none(getattr(request.state, "current_user_id", None))
    # Only log requests for which authentication succeeded.
    if user_id is None:
        return

    tenant_id = _uuid_or_none(getattr(request.state, "tenant_id", None))
    resource_type, resource_id = _get_resource_context(request)
    try:
        async with middleware_async_session(request) as db:
            # Clear stale tenant context in test-overridden sessions. A missing
            # tenant remains a platform-level audit event, as before.
            if tenant_id is None:
                db.info.pop("tenant_id", None)
            else:
                db.info["tenant_id"] = tenant_id

            request_id = getattr(request.state, "request_id", None)
            if isinstance(request_id, str) and request_id:
                db.info["request_id"] = request_id[:100]

            try:
                await AsyncAuditService(db).log_event(
                    event_type=AuditEventType.ACCESS_DENIED,
                    user_id=user_id,
                    email=getattr(request.state, "current_user_email", None),
                    ip_address=(request.client.host if request.client else None),
                    user_agent=request.headers.get("user-agent"),
                    resource_type=resource_type,
                    resource_id=resource_id,
                )
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("Failed to roll back denied-access audit session")
                raise
    except Exception:
        logger.exception("Failed to audit denied resource access")


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc

    if exc.status_code == status.HTTP_404_NOT_FOUND:
        await _audit_resource_access_denied(request)

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
        "Validation error: %s %s - %d validation errors",
        request.method,
        request.url.path,
        len(exc.errors()),
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


async def integrity_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, IntegrityError):
        raise exc

    constraint_name = getattr(
        getattr(exc.orig, "diag", None),
        "constraint_name",
        None,
    )

    if constraint_name in {
        "users_email_key",
        "ix_users_email",
    }:
        message = "Email is already registered."
    else:
        message = "The request conflicts with existing data."

    logger.warning(
        "Database integrity error: %s %s constraint=%s",
        request.method,
        request.url.path,
        constraint_name,
    )

    response: APIResponse[None] = APIResponse(
        success=False,
        message=message,
        data=None,
        errors=None,
    )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=response.model_dump(),
    )


async def database_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, SQLAlchemyError):
        raise exc

    logger.exception(
        "Database error while processing %s %s",
        request.method,
        request.url.path,
    )

    response: APIResponse[None] = APIResponse(
        success=False,
        message="A database error occurred.",
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
        "Unexpected error while processing %s %s",
        request.method,
        request.url.path,
    )

    response: APIResponse[None] = APIResponse(
        success=False,
        message="An unexpected error occurred.",
        data=None,
        errors=None,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(),
    )
