"""Capture successful authenticated reads of high-value FinPilot resources."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.async_session import middleware_async_session
from app.services.async_audit_service import AsyncAuditService

logger = logging.getLogger(__name__)

_PROTECTED_PREFIXES = (
    "/api/v1/customers",
    "/api/v1/documents",
    "/api/v1/files",
    "/api/v1/verification",
    "/api/v1/compliance",
    "/api/v1/reports",
    "/api/v1/workflows",
    "/api/v1/transactions",
    "/api/v1/tasks",
    "/api/v1/audit-events",
    "/api/v1/transaction-risk-analysis",
    "/api/v1/transaction-anomalies",
    "/api/v1/transaction-monitoring",
    "/api/v1/customer-risk-profiles",
    "/api/v1/document-fraud",
    "/api/v1/ai-assistant",
    "/api/v1/ai-risk-recommendations",
    "/api/v1/ai-usage",
    "/api/v1/ai-model-metrics",
    "/api/v1/aml-rules",
    "/api/v1/entity-intelligence",
    "/api/v1/knowledge-documents",
    "/api/v1/users",
    "/api/v1/profile",
    "/api/v1/organizations",
    "/api/v1/tenants",
    "/api/v1/integrations",
    "/api/v1/webhooks",
    "/api/v1/api-keys",
    "/api/v1/subscriptions",
    "/api/v1/system-configurations",
    "/api/v1/security",
    "/api/v1/notifications",
    "/api/v1/analytics",
    "/api/v1/dashboard",
)
_ENTITY_SEGMENTS = {
    "customers",
    "documents",
    "files",
    "verification-cases",
    "verification",
    "compliance-cases",
    "compliance",
    "reports",
    "workflows",
    "transactions",
    "tasks",
    "audit-events",
}


def _resource_from_path(path: str) -> tuple[str, UUID | None]:
    segments = [segment for segment in path.strip("/").split("/") if segment]
    entity_type = next(
        (segment for segment in segments if segment in _ENTITY_SEGMENTS),
        "api_resource",
    )
    entity_id: UUID | None = None
    for segment in segments:
        try:
            entity_id = UUID(segment)
            break
        except ValueError:
            continue
    return entity_type, entity_id


async def _persist_read_audit_event(
    *,
    request: Request,
    user_id: UUID,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict[str, Any],
) -> None:
    async with middleware_async_session(request) as db:
        db.info["tenant_id"] = tenant_id
        db.info["tenant_user_id"] = user_id
        await AsyncAuditService(db).record_data_access(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            access_type="READ",
            metadata=metadata,
        )
        await db.commit()


class AuditAccessMiddleware(BaseHTTPMiddleware):
    """Record protected GETs after the endpoint returns a successful response."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if (
            request.method != "GET"
            or response.status_code < 200
            or response.status_code >= 400
            or not path.startswith(_PROTECTED_PREFIXES)
        ):
            return response

        raw_user_id = getattr(request.state, "current_user_id", None)
        raw_tenant_id = getattr(request.state, "tenant_id", None)
        if raw_user_id is None or raw_tenant_id is None:
            return response

        try:
            user_id = UUID(str(raw_user_id))
            tenant_id = UUID(str(raw_tenant_id))
            route = request.scope.get("route")
            route_template = getattr(route, "path", path)[:500]
            entity_type, entity_id = _resource_from_path(path)
            metadata = {
                "method": "GET",
                "route": route_template,
                "status_code": response.status_code,
                "request_id": getattr(request.state, "request_id", None),
            }
            await _persist_read_audit_event(
                request=request,
                user_id=user_id,
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=metadata,
            )
        except Exception:
            # Do not turn an already-successful business response into a 500.
            logger.exception("Failed to persist protected-read audit event")
        return response
