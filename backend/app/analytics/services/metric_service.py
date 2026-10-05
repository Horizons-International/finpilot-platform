from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.analytics.metrics.engine import MetricEngine
from app.analytics.metrics.measure_provider import MetricMeasureProvider
from app.analytics.models.metric_definition import MetricDefinition
from app.analytics.models.metric_result import MetricResult
from app.analytics.repositories.metric_repository import MetricRepository
from app.schemas.metrics import (
    MetricCalculationRequest,
    MetricDefinitionCreate,
    MetricDefinitionUpdate,
    MetricResultResponse,
)
from app.utils.date_time import utc_now
from app.utils.enums import (
    MetricCategory,
    MetricStatus,
)
from app.utils.errors import bad_request, not_found


class MetricService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MetricRepository(db)

        self.engine = MetricEngine(
            MetricMeasureProvider(db),
        )

    def create_definition(
        self,
        *,
        data: MetricDefinitionCreate,
    ) -> MetricDefinition:
        if (
            self.repository.get_definition_by_key(
                data.key,
            )
            is not None
        ):
            raise bad_request(
                "A metric with this key already exists.",
            )

        metric = MetricDefinition(
            key=data.key,
            name=data.name,
            description=data.description,
            category=data.category,
            value_type=data.value_type,
            definition=data.definition.model_dump(
                mode="json",
            ),
            status=data.status,
        )

        self.repository.create_definition(metric)
        self.db.commit()
        self.db.refresh(metric)

        return metric

    def list_definitions(
        self,
        *,
        category: MetricCategory | None = None,
        status: MetricStatus | None = None,
    ) -> list[MetricDefinition]:
        return self.repository.list_definitions(
            category=category,
            status=status,
        )

    def get_definition(
        self,
        definition_id: UUID,
    ) -> MetricDefinition:
        metric = self.repository.get_definition_by_id(
            definition_id,
        )

        if metric is None:
            raise not_found("Metric definition")

        return metric

    def update_definition(
        self,
        *,
        definition_id: UUID,
        data: MetricDefinitionUpdate,
    ) -> MetricDefinition:
        metric = self.repository.get_definition_by_id(
            definition_id,
            for_update=True,
        )

        if metric is None:
            raise not_found("Metric definition")

        if data.name is not None:
            metric.name = data.name

        if data.description is not None:
            metric.description = data.description

        if data.category is not None:
            metric.category = data.category

        if data.value_type is not None:
            metric.value_type = data.value_type

        if data.definition is not None:
            metric.definition = data.definition.model_dump(
                mode="json",
            )

        if data.status is not None:
            metric.status = data.status

        self.repository.update_definition(metric)

        self.db.commit()
        self.db.refresh(metric)

        return metric

    def calculate(
        self,
        *,
        request: MetricCalculationRequest,
    ) -> list[MetricResultResponse]:
        metrics = self.repository.get_active_definitions(
            metric_keys=request.metric_keys,
            category=request.category,
        )

        if request.metric_keys:
            found_keys = {metric.key for metric in metrics}

            missing_keys = sorted(
                set(request.metric_keys) - found_keys,
            )

            if missing_keys:
                raise bad_request(
                    "The following metrics are unavailable or inactive: "
                    + ", ".join(missing_keys),
                )

        calculated_at = utc_now()
        results: list[MetricResultResponse] = []

        for metric in metrics:
            value = self.engine.calculate(
                metric=metric,
                start_date=request.start_date,
                end_date=request.end_date,
            )

            result = self.repository.save_result(
                metric_definition_id=metric.id,
                period_start=request.start_date,
                period_end=request.end_date,
                value=value,
                calculated_at=calculated_at,
            )

            results.append(
                self._result_response(
                    result=result,
                    metric=metric,
                )
            )

        self.db.commit()

        return results

    def get_results(
        self,
        *,
        start_date: date,
        end_date: date,
        category: MetricCategory | None = None,
        metric_key: str | None = None,
    ) -> list[MetricResultResponse]:
        rows = self.repository.list_results(
            period_start=start_date,
            period_end=end_date,
            category=category,
            metric_key=metric_key,
        )

        return [
            self._result_response(
                result=result,
                metric=metric,
            )
            for result, metric in rows
        ]

    @staticmethod
    def _result_response(
        *,
        result: MetricResult,
        metric: MetricDefinition,
    ) -> MetricResultResponse:
        return MetricResultResponse(
            id=result.id,
            metric_key=metric.key,
            metric_name=metric.name,
            category=metric.category,
            value_type=metric.value_type,
            period_start=result.period_start,
            period_end=result.period_end,
            value=(None if result.value is None else float(result.value)),
            calculated_at=result.calculated_at,
        )
