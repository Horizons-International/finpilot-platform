from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.utils.enums import MetricCategory, MetricStatus


class MetricRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_definition(
        self,
        definition: MetricDefinition,
    ) -> MetricDefinition:
        self.db.add(definition)
        self.db.flush()
        self.db.refresh(definition)

        return definition

    def get_definition_by_id(
        self,
        definition_id: UUID,
        *,
        for_update: bool = False,
    ) -> MetricDefinition | None:
        statement = select(MetricDefinition).where(
            MetricDefinition.id == definition_id,
        )

        if for_update:
            statement = statement.with_for_update()

        return self.db.scalar(statement)

    def get_definition_by_key(
        self,
        key: str,
    ) -> MetricDefinition | None:
        return self.db.scalar(
            select(MetricDefinition).where(
                MetricDefinition.key == key,
            )
        )

    def list_definitions(
        self,
        *,
        category: MetricCategory | None = None,
        status: MetricStatus | None = None,
    ) -> list[MetricDefinition]:
        statement = select(MetricDefinition).order_by(
            MetricDefinition.category.asc(),
            MetricDefinition.key.asc(),
        )

        if category is not None:
            statement = statement.where(
                MetricDefinition.category == category,
            )

        if status is not None:
            statement = statement.where(
                MetricDefinition.status == status,
            )

        return list(
            self.db.scalars(statement).all(),
        )

    def update_definition(
        self,
        definition: MetricDefinition,
    ) -> MetricDefinition:
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
            MetricDefinition.status == MetricStatus.ACTIVE,
        )

        if metric_keys:
            statement = statement.where(
                MetricDefinition.key.in_(metric_keys),
            )

        if category is not None:
            statement = statement.where(
                MetricDefinition.category == category,
            )

        statement = statement.order_by(
            MetricDefinition.key.asc(),
        )

        return list(
            self.db.scalars(statement).all(),
        )

    def save_result(
        self,
        *,
        metric_definition_id: UUID,
        period_start: date,
        period_end: date,
        value: float | None,
        calculated_at: datetime,
    ) -> MetricResult:
        result = self.db.scalar(
            select(MetricResult).where(
                MetricResult.metric_definition_id == metric_definition_id,
                MetricResult.period_start == period_start,
                MetricResult.period_end == period_end,
            )
        )

        if result is None:
            result = MetricResult(
                metric_definition_id=metric_definition_id,
                period_start=period_start,
                period_end=period_end,
            )
            self.db.add(result)

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
            select(
                MetricResult,
                MetricDefinition,
            )
            .join(
                MetricDefinition,
                MetricDefinition.id == MetricResult.metric_definition_id,
            )
            .where(
                MetricResult.period_start == period_start,
                MetricResult.period_end == period_end,
            )
        )

        if category is not None:
            statement = statement.where(
                MetricDefinition.category == category,
            )

        if metric_key is not None:
            statement = statement.where(
                MetricDefinition.key == metric_key,
            )

        statement = statement.order_by(
            MetricDefinition.category.asc(),
            MetricDefinition.key.asc(),
        )

        return [
            (metric_result, metric_definition)
            for metric_result, metric_definition in self.db.execute(statement).all()
        ]
