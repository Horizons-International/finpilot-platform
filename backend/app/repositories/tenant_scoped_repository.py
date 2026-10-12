from collections.abc import Mapping
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


def resolve_tenant_id(
    db: Session,
    tenant_id: UUID | None = None,
    *,
    required: bool = True,
) -> UUID | None:
    """Resolve a tenant from trusted service input or the authenticated session.

    When both are supplied they must agree. This avoids accidentally using a
    repository configured for a different tenant than the current request.
    """
    session_info = getattr(db, "info", None)
    # Test doubles such as MagicMock expose arbitrary attributes; only a real
    # mapping is a trustworthy SQLAlchemy Session.info container.
    session_tenant_id = (
        session_info.get("tenant_id") if isinstance(session_info, Mapping) else None
    )

    if session_tenant_id is not None and not isinstance(session_tenant_id, UUID):
        raise ValueError("Session tenant context must be a UUID.")

    if tenant_id is not None and session_tenant_id is not None:
        if tenant_id != session_tenant_id:
            raise ValueError(
                "Repository tenant does not match the active session tenant."
            )

    resolved = tenant_id if tenant_id is not None else session_tenant_id

    if resolved is None and required:
        raise ValueError(
            "Tenant context is required for tenant-scoped repository access."
        )

    if resolved is not None and not isinstance(resolved, UUID):
        raise ValueError("Tenant context must be a UUID.")

    return resolved


class TenantScopedRepository(Generic[ModelT]):
    """Repository base for ORM models with a direct ``tenant_id`` column."""

    def __init__(
        self,
        db: Session,
        model: type[ModelT],
        tenant_id: UUID,
    ) -> None:
        if not hasattr(model, "tenant_id"):
            raise TypeError(f"{model.__name__} does not define tenant_id.")

        resolved_tenant_id = resolve_tenant_id(db, tenant_id)
        assert resolved_tenant_id is not None

        self.db = db
        self.model = model
        self.tenant_id = resolved_tenant_id

    def query(self) -> Query[ModelT]:
        """Return a query explicitly restricted to this tenant."""
        return self.db.query(self.model).filter(
            getattr(self.model, "tenant_id") == self.tenant_id,
        )

    def get_by_id(self, entity_id: UUID) -> ModelT | None:
        return self.query().filter(getattr(self.model, "id") == entity_id).first()

    def get_all(self) -> list[ModelT]:
        return self.query().all()

    def create(self, entity: ModelT) -> ModelT:
        """Set tenant ownership from trusted repository context before insert."""
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id is not None and entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot create an entity for another tenant.")

        setattr(entity, "tenant_id", self.tenant_id)
        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)
        return entity

    def update(self, entity: ModelT) -> ModelT:
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot update an entity owned by another tenant.")

        self.db.flush()
        self.db.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot delete an entity owned by another tenant.")

        self.db.delete(entity)
        self.db.flush()
