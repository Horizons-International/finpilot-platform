"""Tenant-scoped async persistence for configurable metrics."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.utils.enums import MetricCategory, MetricStatus


class AsyncMetricRepository:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Metric repository tenant does not match the session.")
        db.info["tenant_id"] = tenant_id
        self.db, self.tenant_id = db, tenant_id

    async def create_definition(self, item: MetricDefinition) -> MetricDefinition:
        if item.tenant_id not in (None, self.tenant_id):
            raise ValueError("Cannot create a metric definition for another tenant.")
        item.tenant_id = self.tenant_id
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_definition(
        self, item_id: UUID, *, for_update: bool = False
    ) -> MetricDefinition | None:
        stmt = select(MetricDefinition).where(
            MetricDefinition.id == item_id, MetricDefinition.tenant_id == self.tenant_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def get_by_key(self, key: str) -> MetricDefinition | None:
        return await self.db.scalar(
            select(MetricDefinition).where(
                MetricDefinition.key == key,
                MetricDefinition.tenant_id == self.tenant_id,
            )
        )

    async def list_definitions(
        self,
        *,
        category: MetricCategory | None = None,
        status: MetricStatus | None = None,
    ) -> list[MetricDefinition]:
        stmt = select(MetricDefinition).where(
            MetricDefinition.tenant_id == self.tenant_id
        )
        if category is not None:
            stmt = stmt.where(MetricDefinition.category == category)
        if status is not None:
            stmt = stmt.where(MetricDefinition.status == status)
        result = await self.db.scalars(
            stmt.order_by(MetricDefinition.category, MetricDefinition.key)
        )
        return list(result.all())

    async def active_definitions(
        self, *, keys: list[str] | None = None, category: MetricCategory | None = None
    ) -> list[MetricDefinition]:
        stmt = select(MetricDefinition).where(
            MetricDefinition.tenant_id == self.tenant_id,
            MetricDefinition.status == MetricStatus.ACTIVE,
        )
        if keys:
            stmt = stmt.where(MetricDefinition.key.in_(keys))
        if category is not None:
            stmt = stmt.where(MetricDefinition.category == category)
        result = await self.db.scalars(stmt.order_by(MetricDefinition.key))
        return list(result.all())

    async def save_result(
        self,
        *,
        definition_id: UUID,
        start: date,
        end: date,
        value: float | None,
        calculated_at: datetime,
    ) -> MetricResult:
        if await self.get_definition(definition_id) is None:
            raise ValueError("Metric definition was not found for this tenant.")
        row = await self.db.scalar(
            select(MetricResult)
            .where(
                MetricResult.tenant_id == self.tenant_id,
                MetricResult.metric_definition_id == definition_id,
                MetricResult.period_start == start,
                MetricResult.period_end == end,
            )
            .with_for_update()
        )
        if row is None:
            row = MetricResult(
                tenant_id=self.tenant_id,
                metric_definition_id=definition_id,
                period_start=start,
                period_end=end,
            )
            self.db.add(row)
        elif row.tenant_id != self.tenant_id:
            raise ValueError("Cannot update a metric result owned by another tenant.")
        row.value = None if value is None else Decimal(str(value))
        row.calculated_at = calculated_at
        await self.db.flush()
        return row

    async def list_results(
        self,
        *,
        start: date,
        end: date,
        category: MetricCategory | None = None,
        metric_key: str | None = None,
    ) -> list[tuple[MetricResult, MetricDefinition]]:
        stmt = (
            select(MetricResult, MetricDefinition)
            .join(
                MetricDefinition,
                MetricDefinition.id == MetricResult.metric_definition_id,
            )
            .where(
                MetricResult.tenant_id == self.tenant_id,
                MetricDefinition.tenant_id == self.tenant_id,
                MetricResult.period_start == start,
                MetricResult.period_end == end,
            )
        )
        if category is not None:
            stmt = stmt.where(MetricDefinition.category == category)
        if metric_key is not None:
            stmt = stmt.where(MetricDefinition.key == metric_key)
        rows = await self.db.execute(
            stmt.order_by(MetricDefinition.category, MetricDefinition.key)
        )
        return [(result, definition) for result, definition in rows.all()]
