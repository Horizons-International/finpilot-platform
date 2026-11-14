"""Asynchronous evaluator for configurable metric definitions."""

from datetime import date

from app.analytics.metrics.async_measure_provider import AsyncMetricMeasureProvider
from app.analytics.models.metric_definition import MetricDefinition
from app.schemas.metrics import AverageDurationMetricDefinition, RatioMetricDefinition


class AsyncMetricEngine:
    def __init__(self, provider: AsyncMetricMeasureProvider) -> None:
        self.provider = provider

    async def calculate(
        self, *, metric: MetricDefinition, start_date: date, end_date: date
    ) -> float | None:
        definition = metric.definition
        metric_type = definition.get("type")
        if metric_type == "ratio":
            parsed = RatioMetricDefinition.model_validate(definition)
            numerator = await self.provider.get(
                measure=parsed.numerator, start_date=start_date, end_date=end_date
            )
            denominator = await self.provider.get(
                measure=parsed.denominator, start_date=start_date, end_date=end_date
            )
            if numerator is None or denominator in (None, 0):
                return None
            return round(numerator / denominator * parsed.multiplier, parsed.precision)
        if metric_type == "average_duration":
            parsed_duration = AverageDurationMetricDefinition.model_validate(definition)
            value = await self.provider.get(
                measure=parsed_duration.measure,
                start_date=start_date,
                end_date=end_date,
            )
            return None if value is None else round(value, parsed_duration.precision)
        raise ValueError(f"Unsupported metric calculation type: '{metric_type}'.")
