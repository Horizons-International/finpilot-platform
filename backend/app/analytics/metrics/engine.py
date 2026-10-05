from datetime import date

from app.analytics.metrics.measure_provider import MetricMeasureProvider
from app.analytics.models.metric_definition import MetricDefinition
from app.schemas.metrics import (
    AverageDurationMetricDefinition,
    RatioMetricDefinition,
)


class MetricEngine:
    """Evaluates configurable metric definitions."""

    def __init__(
        self,
        measure_provider: MetricMeasureProvider,
    ) -> None:
        self.measure_provider = measure_provider

    def calculate(
        self,
        *,
        metric: MetricDefinition,
        start_date: date,
        end_date: date,
    ) -> float | None:
        parsed = self._parse_definition(
            metric.definition,
        )

        if isinstance(
            parsed,
            RatioMetricDefinition,
        ):
            return self._calculate_ratio(
                parsed,
                start_date,
                end_date,
            )

        return self._calculate_average_duration(
            parsed,
            start_date,
            end_date,
        )

    @staticmethod
    def _parse_definition(
        definition: dict,
    ) -> RatioMetricDefinition | AverageDurationMetricDefinition:
        metric_type = definition.get("type")

        if metric_type == "ratio":
            return RatioMetricDefinition.model_validate(
                definition,
            )

        if metric_type == "average_duration":
            return AverageDurationMetricDefinition.model_validate(
                definition,
            )

        raise ValueError(
            f"Unsupported metric calculation type: '{metric_type}'.",
        )

    def _calculate_ratio(
        self,
        definition: RatioMetricDefinition,
        start_date: date,
        end_date: date,
    ) -> float | None:
        numerator = self.measure_provider.get(
            measure=definition.numerator,
            start_date=start_date,
            end_date=end_date,
        )

        denominator = self.measure_provider.get(
            measure=definition.denominator,
            start_date=start_date,
            end_date=end_date,
        )

        if numerator is None or denominator in (None, 0):
            return None

        value = numerator / denominator * definition.multiplier

        return round(
            value,
            definition.precision,
        )

    def _calculate_average_duration(
        self,
        definition: AverageDurationMetricDefinition,
        start_date: date,
        end_date: date,
    ) -> float | None:
        value = self.measure_provider.get(
            measure=definition.measure,
            start_date=start_date,
            end_date=end_date,
        )

        if value is None:
            return None

        return round(
            value,
            definition.precision,
        )
