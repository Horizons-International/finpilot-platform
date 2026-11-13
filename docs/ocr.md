# OCR framework

## Current implementation

The OCR package provides a provider-neutral request, response and service boundary for extracting text from uploaded customer documents. The current provider factory in `backend/app/ocr/providers/factory.py` supports **`OCR_PROVIDER=mock`**. Selecting another provider is not supported until a corresponding adapter is implemented and registered.

This is an integration seam and mock workflow, not a claim that a production OCR engine is configured.

## Processing path

```text
Customer document / OCR request
          |
          v
OCR service
          |
          v
OCR provider interface
          |
          v
Configured provider (currently mock)
          |
          v
Normalized OCR response and processing status
```

Implementation:
- Provider interface and factory: `backend/app/ocr/providers/`
- Mock provider: `backend/app/ocr/providers/mock.py`
- Request/response schemas: `backend/app/ocr/schemas/`
- Service and dependencies: `backend/app/ocr/services/`
- HTTP integration: `backend/app/api/ocr.py`

## Configuration

```dotenv
OCR_PROVIDER=mock
```

The application config also exposes `VERIFICATION_PROVIDER` and `EXTRACTION_PROVIDER`; these select separate workflows and must not be confused with OCR. See [backend/.env.example](../backend/.env.example).

## Status lifecycle

The OCR processing states are:
- `submitted`
- `processing`
- `completed`
- `failed`

The API schema and persisted processing record are authoritative for the exact fields and state transitions.

## Operational and security requirements

Before adding a real OCR engine, define document types, language/quality expectations, file-size/page limits, request timeouts, retry/idempotency behavior, result validation, confidence interpretation, retention and vendor/data-residency controls. Protect source images and extracted text as sensitive customer data. Avoid logging document contents or OCR text.

Do not use OCR output as verified identity evidence without the platform's configured review/approval flow and human checks.

## Evaluator checks

- Use synthetic test documents only.
- Verify upload access and tenant ownership before triggering OCR.
- Confirm provider failures are represented as failed processing, not a fabricated successful extraction.
- Check whether the configured provider is mock and disclose this in the evaluation record.
- Use `/docs` to confirm the running API route and request schema.
