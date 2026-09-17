import json

from openai import OpenAI

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.providers.base import AIProvider
from app.ai.schemas.config import AIConfig
from app.ai.schemas.requests import AIRequest, AIRequestType
from app.ai.schemas.responses import AIResponse

COMPLIANCE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
        },
        "customer_status": {
            "type": "string",
        },
        "missing_documents": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "recommendation": {
            "type": "string",
        },
        "confidence": {
            "type": "number",
        },
    },
    "required": [
        "summary",
        "customer_status",
        "missing_documents",
        "findings",
        "recommendation",
        "confidence",
    ],
    "additionalProperties": False,
}


class OpenAIProvider(AIProvider):
    def __init__(self, config: AIConfig) -> None:
        if not config.api_key:
            raise AIConfigurationError(
                "AI_API_KEY is required for the OpenAI provider."
            )

        if not config.model:
            raise AIConfigurationError("AI_MODEL is required for the OpenAI provider.")

        self.config = config

        self.client = OpenAI(
            api_key=config.api_key,
            timeout=config.timeout,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        if not request.prompt.strip():
            raise AIProviderError("AI prompt cannot be empty.")

        if request.request_type != AIRequestType.COMPLIANCE_ASSISTANT:
            raise AIProviderError(
                "OpenAI provider currently supports compliance assistant requests only."
            )

        try:
            response = self.client.responses.create(
                model=self.config.model,
                input=request.prompt,
                max_output_tokens=self.config.max_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "compliance_assistant_response",
                        "description": ("Structured compliance assistant response."),
                        "strict": True,
                        "schema": COMPLIANCE_RESPONSE_SCHEMA,
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

        return AIResponse(
            provider_name="openai",
            request_type=request.request_type.value,
            content=content,
            structured_data=structured_data,
            request_id=None,
        )
