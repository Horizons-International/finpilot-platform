"""Provider registry used to resolve adapters without coupling core logic to vendors."""

from collections.abc import Callable
from typing import Any

from app.integrations.adapters.base import IntegrationAdapter
from app.integrations.providers.mock import MockIntegrationAdapter
from app.utils.enums import IntegrationType

AdapterFactory = Callable[[dict[str, Any]], IntegrationAdapter]


class IntegrationAdapterRegistry:
    """Registry keyed by normalized provider name and integration type."""

    def __init__(self) -> None:
        self._factories: dict[tuple[str, IntegrationType], AdapterFactory] = {}

    def register(
        self,
        provider_name: str,
        integration_type: IntegrationType,
        factory: AdapterFactory,
        *,
        replace: bool = False,
    ) -> None:
        key = (provider_name.strip().lower(), integration_type)
        if not key[0]:
            raise ValueError("Provider name cannot be empty.")
        if key in self._factories and not replace:
            raise ValueError(
                f"Adapter already registered for provider '{key[0]}' "
                f"and type '{integration_type.value}'."
            )
        self._factories[key] = factory

    def supports(
        self,
        provider_name: str,
        integration_type: IntegrationType,
    ) -> bool:
        return (provider_name.strip().lower(), integration_type) in self._factories

    def create(
        self,
        provider_name: str,
        integration_type: IntegrationType,
        configuration: dict[str, Any],
    ) -> IntegrationAdapter:
        key = (provider_name.strip().lower(), integration_type)
        factory = self._factories.get(key)
        if factory is None:
            raise KeyError(
                f"No adapter registered for provider '{key[0]}' "
                f"and type '{integration_type.value}'."
            )
        adapter = factory(configuration)
        if not isinstance(adapter, IntegrationAdapter):
            raise TypeError(
                "An integration adapter factory returned an invalid adapter."
            )
        return adapter


adapter_registry = IntegrationAdapterRegistry()

# A clearly labelled mock adapter is available for all supported integration
# types. It is useful for exercising lifecycle and status tracking in development;
# it does not contact an external system.
for _integration_type in IntegrationType:
    adapter_registry.register("mock", _integration_type, MockIntegrationAdapter)


def register_adapter(
    provider_name: str,
    integration_type: IntegrationType,
    factory: AdapterFactory,
    *,
    replace: bool = False,
) -> None:
    """Public helper for registering provider adapters during application setup."""
    adapter_registry.register(
        provider_name,
        integration_type,
        factory,
        replace=replace,
    )
