"""Write/search append-only audit events without storing request bodies or secrets."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.repositories.audit_event_repository import AuditEventRepository

_SENSITIVE_KEY = re.compile(
    r"password|token|secret|authorization|credential|document.?number|passport|"
    r"date.?of.?birth|address|phone|ssn|extracted.?text|file.?content|"
    r"request.?body|response.?body",
    re.IGNORECASE,
)
_MAX_DEPTH = 4
_MAX_ITEMS = 100
_MAX_STRING = 1000


def sanitize_audit_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bound JSON metadata and redact credential/document content by key name."""
    if value is None:
        return {}

    def clean(item: Any, depth: int = 0) -> Any:
        if depth > _MAX_DEPTH:
            return "[MAX_DEPTH]"
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, str):
            return item[:_MAX_STRING]
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for index, (key, child) in enumerate(item.items()):
                if index >= _MAX_ITEMS:
                    result["_truncated"] = True
                    break
                safe_key = str(key)[:100]
                result[safe_key] = (
                    "[REDACTED]"
                    if _SENSITIVE_KEY.search(safe_key)
                    else clean(child, depth + 1)
                )
            return result
        if isinstance(item, (list, tuple, set)):
            return [clean(child, depth + 1) for child in list(item)[:_MAX_ITEMS]]
        return str(item)[:_MAX_STRING]

    result = clean(value)
    return result if isinstance(result, dict) else {}


class AuditEventService:
    """Tenant-scoped recorder and search service."""

    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        resolved = tenant_id if tenant_id is not None else db.info.get("tenant_id")
        if resolved is not None and not isinstance(resolved, UUID):
            raise ValueError("Audit tenant context must be a UUID")
        active_tenant = db.info.get("tenant_id")
        if (
            resolved is not None
            and active_tenant is not None
            and active_tenant != resolved
        ):
            raise ValueError(
                "Audit service tenant does not match the active session tenant"
            )
        if resolved is not None:
            db.info["tenant_id"] = resolved
        self.db = db
        self.tenant_id = resolved
        self.repository = AuditEventRepository(db, resolved)

    def record_event(
        self,
        *,
        action: str,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
        tenant_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        resolved_tenant = tenant_id if tenant_id is not None else self.tenant_id
        if resolved_tenant is not None and not isinstance(resolved_tenant, UUID):
            raise ValueError("Audit tenant context must be a UUID")
        active_tenant = self.db.info.get("tenant_id")
        if (
            resolved_tenant is not None
            and active_tenant is not None
            and active_tenant != resolved_tenant
        ):
            raise ValueError(
                "Audit event tenant does not match the active session tenant"
            )
        if resolved_tenant is not None:
            self.db.info["tenant_id"] = resolved_tenant
        normalized_action = action.strip().upper()
        if not normalized_action:
            raise ValueError("Audit action cannot be blank")
        if len(normalized_action) > 100:
            raise ValueError("Audit action must be at most 100 characters")
        normalized_entity = entity_type.strip() if entity_type is not None else None
        if normalized_entity == "":
            normalized_entity = None
        if normalized_entity is not None and len(normalized_entity) > 100:
            raise ValueError("entity_type must be at most 100 characters")
        safe_metadata = sanitize_audit_metadata(metadata)
        if resolved_tenant is None:
            # The tenant guard intentionally rejects ordinary tenant-owned ORM
            # inserts without a tenant. Unknown-email login attempts are the one
            # justified global audit case; use a reviewed, reasoned Core insert
            # so it is not confused with an accidental unscoped ORM write.
            event_id = uuid4()
            values: dict[str, Any] = {
                "id": event_id,
                "tenant_id": None,
                "user_id": user_id,
                "action": normalized_action,
                "entity_type": normalized_entity,
                "entity_id": entity_id,
                "metadata": safe_metadata,
            }
            if timestamp is not None:
                values["timestamp"] = timestamp
            audit_table = cast(Any, AuditEvent.__table__)
            statement = (
                insert(audit_table)
                .values(**values)
                .returning(AuditEvent.__table__.c.timestamp)
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason="record global or anonymous audit evidence",
                )
            )
            stored_timestamp = self.db.execute(statement).scalar_one()
            return AuditEvent(
                id=event_id,
                tenant_id=None,
                user_id=user_id,
                action=normalized_action,
                entity_type=normalized_entity,
                entity_id=entity_id,
                timestamp=stored_timestamp,
                event_metadata=safe_metadata,
            )

        event = AuditEvent(
            tenant_id=resolved_tenant,
            user_id=user_id,
            action=normalized_action,
            entity_type=normalized_entity,
            entity_id=entity_id,
            event_metadata=safe_metadata,
        )
        if timestamp is not None:
            event.timestamp = timestamp
        self.db.add(event)
        self.db.flush()
        return event

    def record_data_access(
        self,
        *,
        user_id: UUID,
        entity_type: str,
        entity_id: UUID | None,
        access_type: str = "READ",
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        payload = dict(metadata or {})
        payload["access_type"] = access_type.upper()[:32]
        return self.record_event(
            action="DATA_ACCESS",
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=payload,
        )

    def search(
        self,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditEvent], int]:
        return self.repository.search(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
            page=page,
            page_size=page_size,
        )


def record_audit_event(
    db: Session,
    *,
    action: str,
    user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Low-level helper for services that already have a trusted DB session."""
    return AuditEventService(db).record_event(
        action=action,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )
