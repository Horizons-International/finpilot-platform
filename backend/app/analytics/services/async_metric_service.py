"""Async tenant-scoped orchestration for configurable metrics."""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.metrics.async_engine import AsyncMetricEngine
from app.analytics.metrics.async_measure_provider import AsyncMetricMeasureProvider
from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.analytics.repositories.async_metric_repository import AsyncMetricRepository
from app.schemas.metrics import (
    MetricCalculationRequest,
    MetricDefinitionCreate,
    MetricDefinitionUpdate,
    MetricResultResponse,
)
from app.utils.date_time import utc_now
from app.utils.enums import MetricCategory, MetricStatus
from app.utils.errors import bad_request, not_found


class AsyncMetricService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = AsyncMetricRepository(db, tenant_id)
        self.engine = AsyncMetricEngine(AsyncMetricMeasureProvider(db, tenant_id))

    async def create_definition(
        self, *, data: MetricDefinitionCreate
    ) -> MetricDefinition:
        if await self.repository.get_by_key(data.key) is not None:
            raise bad_request("A metric with this key already exists.")
        metric = MetricDefinition(
            tenant_id=self.tenant_id,
            key=data.key,
            name=data.name,
            description=data.description,
            category=data.category,
            value_type=data.value_type,
            definition=data.definition.model_dump(mode="json"),
            status=data.status,
        )
        await self.repository.create_definition(metric)
        await self.db.commit()
        await self.db.refresh(metric)
        return metric

    async def list_definitions(
        self,
        *,
        category: MetricCategory | None = None,
        status: MetricStatus | None = None,
    ) -> list[MetricDefinition]:
        return await self.repository.list_definitions(category=category, status=status)

    async def get_definition(self, definition_id: UUID) -> MetricDefinition:
        metric = await self.repository.get_definition(definition_id)
        if metric is None:
            raise not_found("Metric definition")
        return metric

    async def update_definition(
        self, *, definition_id: UUID, data: MetricDefinitionUpdate
    ) -> MetricDefinition:
        metric = await self.repository.get_definition(definition_id, for_update=True)
        if metric is None:
            raise not_found("Metric definition")
        for field in ("name", "description", "category", "value_type", "status"):
            value = getattr(data, field)
            if value is not None:
                setattr(metric, field, value)
        if data.definition is not None:
            metric.definition = data.definition.model_dump(mode="json")
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(metric)
        return metric

    async def calculate(
        self, *, request: MetricCalculationRequest
    ) -> list[MetricResultResponse]:
        if request.start_date > request.end_date:
            raise bad_request("start_date cannot be after end_date.")
        metrics = await self.repository.active_definitions(
            keys=request.metric_keys, category=request.category
        )
        if request.metric_keys:
            missing = sorted(
                set(request.metric_keys) - {metric.key for metric in metrics}
            )
            if missing:
                raise bad_request(
                    "The following metrics are unavailable or inactive: "
                    + ", ".join(missing)
                )
        calculated_at = utc_now()
        output: list[MetricResultResponse] = []
        for metric in metrics:
            if metric.tenant_id != self.tenant_id:
                raise ValueError("Metric definition tenant mismatch.")
            value = await self.engine.calculate(
                metric=metric, start_date=request.start_date, end_date=request.end_date
            )
            result = await self.repository.save_result(
                definition_id=metric.id,
                start=request.start_date,
                end=request.end_date,
                value=value,
                calculated_at=calculated_at,
            )
            output.append(self._response(result, metric))
        await self.db.commit()
        return output

    async def get_results(
        self,
        *,
        start_date: date,
        end_date: date,
        category: MetricCategory | None = None,
        metric_key: str | None = None,
    ) -> list[MetricResultResponse]:
        if start_date > end_date:
            raise bad_request("start_date cannot be after end_date.")
        rows = await self.repository.list_results(
            start=start_date, end=end_date, category=category, metric_key=metric_key
        )
        return [self._response(result, metric) for result, metric in rows]

    @staticmethod
    def _response(
        result: MetricResult, metric: MetricDefinition
    ) -> MetricResultResponse:
        return MetricResultResponse(
            id=result.id,
            metric_key=metric.key,
            metric_name=metric.name,
            category=metric.category,
            value_type=metric.value_type,
            period_start=result.period_start,
            period_end=result.period_end,
            value=None if result.value is None else float(result.value),
            calculated_at=result.calculated_at,
        )
