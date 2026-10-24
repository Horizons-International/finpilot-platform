# Webhooks

Webhook subscriptions are managed at `/api/v1/webhooks`. Creating, listing, updating, and inspecting subscriptions uses a JWT-authenticated account with the required role (the API currently requires an Administrator for subscription creation/listing).

## Create a subscription

```json
{
  "endpoint_url": "https://partner.example.com/finpilot/events",
  "event_types": ["customer.created", "customer.updated"]
}
```

The callback URL must use HTTPS and a publicly addressable host. The API rejects user-info, fragments, query parameters, localhost/private/reserved addresses, and unsupported event names. The currently declared event types are:

- `customer.created`
- `customer.updated`
- `verification.completed`
- `verification.failed`
- `case.created`
- `case.closed`

## Verify and process events

A representative event has this shape:

```json
{
  "id": "event-uuid",
  "type": "customer.created",
  "created_at": "2026-01-01T12:00:00+00:00",
  "data": { "id": "customer-uuid", "status": "NEW" }
}
```

FinPilot documents the response signing header as `X-FinPilot-Signature`; the signing secret is returned once during subscription creation. Keep the secret private and verify the signature against the exact raw request body using the current signature format implemented by your deployed release before trusting the payload. Do not parse/reserialize JSON before signature verification.

## Reliability guidance

Make handlers idempotent using the event ID, respond quickly, and offload long-running work to a queue. Expect retries and occasional duplicate deliveries. Use webhook delivery/history endpoints from `/docs` to inspect status and failures. The event payloads are intentionally compact and should not be treated as a replacement for an authorized API read.
