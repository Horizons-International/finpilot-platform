import json

from openai import AsyncOpenAI

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.providers.async_base import AsyncAIProvider
from app.ai.providers.openai import (
    AML_INVESTIGATION_RESPONSE_SCHEMA,
    ANALYTICS_RESPONSE_SCHEMA,
    COMPLIANCE_RESPONSE_SCHEMA,
    DOCUMENT_FRAUD_RESPONSE_SCHEMA,
    TRANSACTION_RISK_RESPONSE_SCHEMA,
)
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse

_RESPONSE_FORMATS = {
    AIRequestType.COMPLIANCE_ASSISTANT: (
        COMPLIANCE_RESPONSE_SCHEMA,
        "compliance_assistant_response",
        "Structured compliance assistant response.",
    ),
    AIRequestType.ANALYTICS_ASSISTANT: (
        ANALYTICS_RESPONSE_SCHEMA,
        "analytics_assistant_response",
        "Structured business analytics response.",
    ),
    AIRequestType.TRANSACTION_RISK_ANALYSIS: (
        TRANSACTION_RISK_RESPONSE_SCHEMA,
        "transaction_risk_analysis_response",
        "AI-assisted transaction risk review recommendation.",
    ),
    AIRequestType.AML_INVESTIGATION_ASSISTANT: (
        AML_INVESTIGATION_RESPONSE_SCHEMA,
        "aml_investigation_assistant_response",
        "Structured AI-assisted AML investigation response.",
    ),
    AIRequestType.DOCUMENT_FRAUD_ANALYSIS: (
        DOCUMENT_FRAUD_RESPONSE_SCHEMA,
        "document_fraud_analysis_response",
        "AI-assisted document authenticity review observations.",
    ),
}


class AsyncOpenAIProvider(AsyncAIProvider):
    """OpenAI Responses API adapter backed by the SDK's async HTTP client."""

    def __init__(self, config: AIConfig, client: AsyncOpenAI | None = None) -> None:
        if not config.api_key:
            raise AIConfigurationError(
                "AI_API_KEY is required for the OpenAI provider."
            )
        if not config.model:
            raise AIConfigurationError("AI_MODEL is required for the OpenAI provider.")

        self.config = config
        self.client = client or AsyncOpenAI(
            api_key=config.api_key,
            timeout=config.timeout,
        )

    async def generate(self, request: AIRequest) -> AIResponse:
        if not request.prompt.strip():
            raise AIProviderError("AI prompt cannot be empty.")

        response_format = _RESPONSE_FORMATS.get(request.request_type)
        if response_format is None:
            raise AIProviderError("OpenAI provider does not support this request type.")

        response_schema, response_name, response_description = response_format
        try:
            response = await self.client.responses.create(
                model=self.config.model,
                input=request.prompt,
                max_output_tokens=self.config.max_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": response_name,
                        "description": response_description,
                        "strict": True,
                        "schema": response_schema,
                    }
                },
            )
        except Exception as exc:
            raise AIProviderError("OpenAI provider request failed.") from exc

        content = response.output_text
        if not content:
            raise AIProviderError("OpenAI provider returned an empty response.")

        try:
            structured_data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                "OpenAI provider returned invalid structured data."
            ) from exc

        if not isinstance(structured_data, dict):
            raise AIProviderError("OpenAI provider returned invalid structured data.")

        usage = response.usage
        return AIResponse(
            provider_name="openai",
            request_type=request.request_type.value,
            content=content,
            structured_data=structured_data,
            request_id=None,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )

    async def aclose(self) -> None:
        """Close the async HTTP connection pool before its event loop exits."""
        await self.client.close()
