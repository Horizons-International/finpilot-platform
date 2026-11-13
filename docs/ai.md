# AI framework and assistant

## Overview

FinPilot provides a provider abstraction for AI-assisted compliance and analytics workflows. The application uses a shared AI service/provider interface so business features are not coupled directly to an external model SDK.

The current provider factory supports:
- `mock` — deterministic development/test behavior; does not call an external model.
- `openai` — the OpenAI Responses API adapter; requires a valid `AI_API_KEY` and `AI_MODEL`.

The checked-in environment template selects `AI_PROVIDER=mock`. Setting a provider name alone does not establish credentials, network access, data-processing approval or production readiness.

## Architecture

```text
Feature/API route
      |
      v
Feature service / AI context retrieval
      |
      v
AIService
      |
      v
AIProvider interface
     / \
    v   v
 Mock  OpenAI
```

Implementation locations:
- Provider contract and adapters: `backend/app/ai/providers/`
- Provider factory: `backend/app/ai/providers/factory.py`
- AI request/response/config schemas: `backend/app/ai/schemas/`
- AI service and dependencies: `backend/app/ai/services/`
- Prompt definitions/loader: `backend/app/ai/prompts/`
- API routes: `backend/app/api/` (assistant, prompt, usage, interaction, RAG, knowledge document and analysis routes).

## Configuration

Example local settings:

```dotenv
AI_PROVIDER=mock
AI_API_KEY=
AI_MODEL=
AI_MODEL_VERSION=unspecified
AI_MAX_TOKENS=1000
AI_TEMPERATURE=0.0
AI_TIMEOUT=30
AI_MAX_CONTEXT_CHARACTERS=30000
```

To select OpenAI, configure `AI_PROVIDER=openai`, provide `AI_API_KEY` and a supported `AI_MODEL`, and set appropriate request timeout and context limits. Use a secret manager for deployed credentials. Review provider terms, jurisdictional/data residency requirements, retention, access, cost and whether the data sent to the model is allowed by policy.

The OpenAI adapter validates its configuration before use and supports the structured request types implemented in `backend/app/ai/providers/openai.py`. Do not assume every AI request accepted by the mock provider is automatically supported by the OpenAI provider; check the provider implementation for the request type.

## Assistant and RAG flows

The compliance and analytics assistant routes combine authenticated platform context with prompt selection and the configured provider. Knowledge documents and retrieval services support retrieval-augmented context where the calling feature uses them.

Supported compliance assistant functions documented in the application include:
- `CASE_SUMMARY`
- `CUSTOMER_SUMMARY`
- `DOCUMENT_REVIEW_SUMMARY`
- `COMPLIANCE_NOTES`
- `ANALYTICS_ASSISTANT`

Other API routers expose AML investigation assistance, transaction-risk analysis and document-fraud analysis. Consult the running OpenAPI schema and the route-specific service for exact inputs and roles.

Prompt records are versioned. Feature consumers should use the prompt loader/assignment mechanism rather than hard-code prompt database queries. Prompt activation/assignment and AI interaction history are managed through dedicated APIs/services.

## Data safety and human review

- Treat all generated content as decision-support, not a final regulated decision.
- Verify outputs against source records, approved policy and qualified staff review.
- Do not send secrets, authentication material or unnecessary personal/document data to an external model.
- Retain the correlation between model/provider, prompt version, resource, request and decision record as required by audit policy.
- Review retrieved context and tenant filtering; an AI prompt must never widen access to another tenant's information.
- Record provider timeout/error behavior, token/cost usage, rate limits and fallback behavior.

Model confidence or a structured output field is not a calibrated assurance that a compliance conclusion is correct.

## Evaluation checklist

1. Start in mock mode to validate route, prompt, context and interaction lifecycle without external calls.
2. Confirm unsupported or unavailable requests fail safely and do not leave misleading successful interaction records.
3. Create two tenants and ensure retrieved customer/case/document context never crosses tenant boundaries.
4. Inspect prompt activation and version history.
5. Only in an approved test environment, configure the OpenAI provider and validate supported request types, timeout behavior and cost monitoring.
6. Compare AI output with ground-truth synthetic scenarios and retain human review evidence.

The live API schema is at `/docs`; inspect `backend/app/ai/providers/factory.py` and the selected adapter for current provider behavior.
