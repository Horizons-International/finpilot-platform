# AI Framework

## Overview

FinPilot provides a centralized AI service layer for integrating
AI capabilities across the platform.

The AI framework separates application logic from individual AI
providers so that providers can be changed or added without modifying
business features.

## Architecture

```text
Application
    ↓
AIService
    ↓
AIProvider
    ↓
LLM Provider
````

The application communicates with `AIService`.

`AIService` communicates with the provider through the `AIProvider`
interface.

Individual provider implementations are responsible for communicating
with external AI systems.

## Package Structure

```text
app/ai/
├── __init__.py
├── exceptions.py
├── schemas/
│   ├── __init__.py
│   ├── requests.py
│   └── responses.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   ├── mock.py
│   └── factory.py
└── services/
    ├── __init__.py
    ├── ai_service.py
    └── dependencies.py
```

## AI Requests

The framework currently supports:

* Text requests
* Document analysis requests
* Structured responses

Example text request:

```python
AIRequest(
    request_type=AIRequestType.TEXT,
    prompt="Summarize this customer.",
)
```

Example document analysis request:

```python
AIRequest(
    request_type=AIRequestType.DOCUMENT_ANALYSIS,
    prompt="Analyze this identity document.",
    document_id=document_id,
    structured=True,
)
```

## AI Responses

All providers return the standardized `AIResponse` model.

A response contains:

* Provider name
* Request type
* Generated content
* Optional structured data
* Optional request ID

Example:

```python
AIResponse(
    provider_name="mock",
    request_type="document_analysis",
    content="Analysis completed.",
    structured_data={
        "document_type": "passport",
        "confidence": 0.98,
    },
)
```

## Providers

Providers implement the `AIProvider` interface.

```python
class AIProvider(ABC):
    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        ...
```

The current implementation is:

```text
MockAIProvider
```

The mock provider is intended for development and testing.

Future providers can be added without changing the `AIService`.

## Provider Configuration

The active provider is selected through configuration:

```text
AI_PROVIDER=mock
```

The provider factory resolves the configured implementation.

## Error Handling

The framework defines:

```text
AIError
├── AIProviderError
├── AIConfigurationError
└── AIResponseError
```

Provider failures are converted to `AIProviderError`.

Invalid provider configuration raises `AIConfigurationError`.

Invalid or unusable provider responses raise `AIResponseError`.

## Logging

AI calls are logged centrally by `AIService`.

The logs include metadata such as:

* Provider
* Request type
* Customer ID when available
* Document ID when available
* Structured-response flag
* Request ID

Raw prompts and document contents should not be logged by default.

## Design Principles

The AI framework follows these principles:

1. Application code depends on `AIService`.
2. `AIService` depends on the `AIProvider` interface.
3. Provider-specific code remains inside provider adapters.
4. AI responses are normalized before returning to application code.
5. Provider failures are handled consistently.
6. AI calls are logged centrally.
7. New providers should not require changes to business services.

