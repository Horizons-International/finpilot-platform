# Error handling

The current exception handlers generally return the API envelope:

```json
{
  "success": false,
  "message": "Validation failed.",
  "data": null,
  "errors": [
    { "field": "email", "message": "Input should be a valid email address" }
  ]
}
```

A few middleware-generated or infrastructure responses may have a different shape. Always inspect the HTTP status and content type as well as the JSON body.

| HTTP status | Meaning | Suggested action |
|---|---|---|
| 400 | Bad request or business rule rejection | Correct the input or workflow state. |
| 401 | Authentication is missing, invalid, expired, or revoked | Sign in again or verify the API key. |
| 403 | Role/resource permission or API-key scope denied | Request the minimum required access; do not retry unchanged. |
| 404 | Resource is not available in the authorized scope | Verify the ID and tenant/access context. |
| 409 | Conflict with an existing record or constraint | Reconcile current state before retrying. |
| 422 | Request validation failed | Use `errors[].field` and `errors[].message` to correct the request. |
| 429 | Rate limit or capacity limit reached | Back off with jitter and honor `Retry-After` if the server sends it. |
| 500 | Unexpected application/database failure | Retry only when safe; provide the request ID to support. |
| 503 | Service/dependency not ready | Retry with bounded exponential backoff. |

## Retry rules

- Do not retry non-idempotent writes automatically unless you can determine whether the original request succeeded.
- Apply exponential backoff with jitter for temporary 429/5xx failures.
- Treat 401/403/422 as caller/configuration problems until corrected.
- Include timestamp, method, path, HTTP status, response message, and request ID (if supplied) in support reports; redact all secrets and sensitive fields.
