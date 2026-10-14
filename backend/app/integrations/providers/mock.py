"""Development adapter that exercises lifecycle behavior without network access."""

from typing import Any

from app.integrations.adapters.base import (
    IntegrationAdapter,
    IntegrationCheckResult,
)
from app.utils.enums import IntegrationStatus


class MockIntegrationAdapter(IntegrationAdapter):
    """Safe placeholder for any integration category.

    It deliberately reports ``DEGRADED`` instead of ``HEALTHY`` because no live
    external endpoint has been contacted.
    """

    def __init__(self, configuration: dict[str, Any]) -> None:
        super().__init__(configuration)

    def validate_configuration(self) -> None:
        if not isinstance(self.configuration, dict):
            raise ValueError("Provider configuration must be a JSON object.")

    def check_connection(self) -> IntegrationCheckResult:
        self.validate_configuration()
        return IntegrationCheckResult(
            status=IntegrationStatus.DEGRADED,
            message=(
                "Mock adapter selected. No live external connection was attempted; "
                "register a real provider adapter to verify connectivity."
            ),
        )
