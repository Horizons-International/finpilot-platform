from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.analytics.tenant_context import resolve_tenant_id
from app.utils.enums import MetricCategory, MetricStatus


class MetricRepository:
    """Tenant-scoped persistence for metric definitions and their results."""

    def __init__(self, db: Session, tenant_id: UUID | None = None) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_id(db, tenant_id)

    def create_definition(self, definition: MetricDefinition) -> MetricDefinition:
        current_tenant = getattr(definition, "tenant_id", None)
        if current_tenant is not None and current_tenant != self.tenant_id:
            raise ValueError("Cannot create a metric definition for another tenant.")
        definition.tenant_id = self.tenant_id
        self.db.add(definition)
        self.db.flush()
        self.db.refresh(definition)
        return definition

    def get_definition_by_id(
        self, definition_id: UUID, *, for_update: bool = False
    ) -> MetricDefinition | None:
        statement = select(MetricDefinition).where(
            MetricDefinition.id == definition_id,
            MetricDefinition.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_definition_by_key(self, key: str) -> MetricDefinition | None:
        return self.db.scalar(
            select(MetricDefinition).where(
                MetricDefinition.key == key,
                MetricDefinition.tenant_id == self.tenant_id,
            )
        )

    def list_definitions(
        self,
        *,
        category: MetricCategory | None = None,
        status: MetricStatus | None = None,
    ) -> list[MetricDefinition]:
        statement = select(MetricDefinition).where(
            MetricDefinition.tenant_id == self.tenant_id
        )
        if category is not None:
            statement = statement.where(MetricDefinition.category == category)
        if status is not None:
            statement = statement.where(MetricDefinition.status == status)
        statement = statement.order_by(
            MetricDefinition.category.asc(), MetricDefinition.key.asc()
        )
        return list(self.db.scalars(statement).all())

    def update_definition(self, definition: MetricDefinition) -> MetricDefinition:
        if definition.tenant_id != self.tenant_id:
            raise ValueError(
                "Cannot update a metric definition owned by another tenant."
            )
        self.db.flush()
        self.db.refresh(definition)
        return definition

    def get_active_definitions(
        self,
        *,
        metric_keys: list[str] | None = None,
        category: MetricCategory | None = None,
    ) -> list[MetricDefinition]:
        statement = select(MetricDefinition).where(
            MetricDefinition.tenant_id == self.tenant_id,
            MetricDefinition.status == MetricStatus.ACTIVE,
        )
        if metric_keys:
            statement = statement.where(MetricDefinition.key.in_(metric_keys))
        if category is not None:
            statement = statement.where(MetricDefinition.category == category)
        statement = statement.order_by(MetricDefinition.key.asc())
        return list(self.db.scalars(statement).all())

    def save_result(
        self,
        *,
        metric_definition_id: UUID,
        period_start: date,
        period_end: date,
        value: float | None,
        calculated_at: datetime,
    ) -> MetricResult:
        # Confirm the definition is owned by this tenant before writing a result.
        definition = self.get_definition_by_id(metric_definition_id)
        if definition is None:
            raise ValueError("Metric definition was not found for this tenant.")

        result = self.db.scalar(
            select(MetricResult).where(
                MetricResult.tenant_id == self.tenant_id,
                MetricResult.metric_definition_id == metric_definition_id,
                MetricResult.period_start == period_start,
                MetricResult.period_end == period_end,
            )
        )
        if result is None:
            result = MetricResult(
                tenant_id=self.tenant_id,
                metric_definition_id=metric_definition_id,
                period_start=period_start,
                period_end=period_end,
            )
            self.db.add(result)
        elif result.tenant_id != self.tenant_id:
            raise ValueError("Cannot update a metric result owned by another tenant.")

        result.value = None if value is None else Decimal(str(value))
        result.calculated_at = calculated_at
        self.db.flush()
        return result

    def list_results(
        self,
        *,
        period_start: date,
        period_end: date,
        category: MetricCategory | None = None,
        metric_key: str | None = None,
    ) -> list[tuple[MetricResult, MetricDefinition]]:
        statement = (
            select(MetricResult, MetricDefinition)
            .join(
                MetricDefinition,
                MetricDefinition.id == MetricResult.metric_definition_id,
            )
            .where(
                MetricResult.tenant_id == self.tenant_id,
                MetricDefinition.tenant_id == self.tenant_id,
                MetricResult.period_start == period_start,
                MetricResult.period_end == period_end,
            )
        )
        if category is not None:
            statement = statement.where(MetricDefinition.category == category)
        if metric_key is not None:
            statement = statement.where(MetricDefinition.key == metric_key)
        statement = statement.order_by(
            MetricDefinition.category.asc(), MetricDefinition.key.asc()
        )
        return [
            (metric_result, metric_definition)
            for metric_result, metric_definition in self.db.execute(statement).all()
        ]
