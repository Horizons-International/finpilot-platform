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

ANALYTICS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
        },
        "suggested_insights": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "confidence": {
            "type": "number",
        },
    },
    "required": [
        "summary",
        "suggested_insights",
        "confidence",
    ],
    "additionalProperties": False,
}


TRANSACTION_RISK_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_score": {"type": "integer"},
        "reason": {"type": "string"},
        "recommended_action": {"type": "string"},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "risk_score",
        "reason",
        "recommended_action",
        "risk_factors",
        "confidence",
    ],
    "additionalProperties": False,
}

AML_INVESTIGATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "customer_overview": {"type": "string"},
        "risk_indicators": {
            "type": "array",
            "items": {"type": "string"},
        },
        "related_activity": {
            "type": "array",
            "items": {"type": "string"},
        },
        "suggested_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number"},
    },
    "required": [
        "summary",
        "customer_overview",
        "risk_indicators",
        "related_activity",
        "suggested_actions",
        "confidence",
    ],
    "additionalProperties": False,
}


DOCUMENT_FRAUD_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "document_quality_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "additional_risk_indicators": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number"},
    },
    "required": [
        "summary",
        "document_quality_notes",
        "additional_risk_indicators",
        "recommended_actions",
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

        if request.request_type == AIRequestType.COMPLIANCE_ASSISTANT:
            response_schema = COMPLIANCE_RESPONSE_SCHEMA
            response_name = "compliance_assistant_response"
            response_description = "Structured compliance assistant response."

        elif request.request_type == AIRequestType.ANALYTICS_ASSISTANT:
            response_schema = ANALYTICS_RESPONSE_SCHEMA
            response_name = "analytics_assistant_response"
            response_description = "Structured business analytics response."

        elif request.request_type == AIRequestType.TRANSACTION_RISK_ANALYSIS:
            response_schema = TRANSACTION_RISK_RESPONSE_SCHEMA
            response_name = "transaction_risk_analysis_response"
            response_description = "AI-assisted transaction risk review recommendation."
        elif request.request_type == AIRequestType.AML_INVESTIGATION_ASSISTANT:
            response_schema = AML_INVESTIGATION_RESPONSE_SCHEMA
            response_name = "aml_investigation_assistant_response"
            response_description = "Structured AI-assisted AML investigation response."
        elif request.request_type == AIRequestType.DOCUMENT_FRAUD_ANALYSIS:
            response_schema = DOCUMENT_FRAUD_RESPONSE_SCHEMA
            response_name = "document_fraud_analysis_response"
            response_description = (
                "AI-assisted document authenticity review observations."
            )
        else:
            raise AIProviderError("OpenAI provider does not support this request type.")

        try:
            response = self.client.responses.create(
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
            raise AIProviderError(
                "OpenAI provider request failed.",
            ) from exc

        content = response.output_text

        if not content:
            raise AIProviderError(
                "OpenAI provider returned an empty response.",
            )

        try:
            structured_data = json.loads(
                content,
            )
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                "OpenAI provider returned invalid structured data.",
            ) from exc

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
