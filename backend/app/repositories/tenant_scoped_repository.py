from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    """Repository for models with a tenant_id column."""

    def __init__(
        self,
        db: Session,
        model: type[ModelT],
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.model = model
        self.tenant_id = tenant_id

    def query(self) -> Query[ModelT]:
        """Return a query restricted to the current tenant."""
        tenant_column = getattr(self.model, "tenant_id")

        return self.db.query(self.model).filter(
            tenant_column == self.tenant_id,
        )

    def get_by_id(self, entity_id: UUID) -> ModelT | None:
        id_column = getattr(self.model, "id")

        return (
            self.query()
            .filter(
                id_column == entity_id,
            )
            .first()
        )

    def get_all(self) -> list[ModelT]:
        return self.query().all()

    def create(self, entity: ModelT) -> ModelT:
        """Assign the tenant from trusted repository context."""
        entity_tenant_id = getattr(entity, "tenant_id", None)

        if entity_tenant_id is not None and entity_tenant_id != self.tenant_id:
            raise ValueError("Cannot create an entity for another tenant.")

        setattr(entity, "tenant_id", self.tenant_id)

        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)

        return entity

    def update(self, entity: ModelT) -> ModelT:
        entity_tenant_id = getattr(entity, "tenant_id")

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
