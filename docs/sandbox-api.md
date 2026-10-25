# FinPilot Sandbox API

Base path: `/api/v1/sandbox`. All data is synthetic and stored only in `sandbox_*` tables. Sandbox keys use the `fp_test_` prefix and the `X-API-Key` header; they are not accepted by production partner endpoints.

## Create an account

```bash
curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/accounts" \
  -H 'Content-Type: application/json' \
  -d '{"organization_name":"Example Bank Sandbox","developer_name":"Alex Developer","developer_email":"alex@example.com"}'
```

The response includes a test API key shown only once, a sandbox organization, one synthetic developer, three sample customers, and an expiration date (30 days). Save the key securely. Do not use real customer data.

## Call sandbox endpoints

```bash
curl "$SANDBOX_BASE_URL/api/v1/sandbox/customers" \
  -H "X-API-Key: $SANDBOX_API_KEY"
```

Create a customer:

```bash
curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/customers" \
  -H "X-API-Key: $SANDBOX_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"external_reference":"YOUR-TEST-001","first_name":"Morgan","last_name":"Example","email":"morgan@example.com","phone_number":"+15550101999","attributes":{"segment":"retail","source":"sandbox-demo"}}'
```

Simulate verification (replace `CUSTOMER_ID`):

```bash
curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/customers/CUSTOMER_ID/verifications" \
  -H "X-API-Key: $SANDBOX_API_KEY" -H 'Content-Type: application/json' \
  -d '{"scenario":"APPROVED"}'
```

Supported scenarios are `APPROVED` -> `VERIFIED`, `REJECTED` -> `REJECTED`, and `MANUAL_REVIEW` -> `REVIEW_REQUIRED`. The simulator never contacts a verification provider.

## Test users

The account-creation response includes a synthetic developer user. Add and list more sandbox users using the account's test key; these are sandbox records, not production login accounts.

```bash
curl "$SANDBOX_BASE_URL/api/v1/sandbox/users" \
  -H "X-API-Key: $SANDBOX_API_KEY"

curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/users" \
  -H "X-API-Key: $SANDBOX_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Verification Reviewer","email":"reviewer@example.com","role":"REVIEWER"}'
```

Allowed sandbox roles are `DEVELOPER`, `OPERATOR`, `REVIEWER`, and `AUDITOR`.

## API-key management

The initial key has `sandbox:admin`, `sandbox:read`, `sandbox:write`, and `sandbox:webhooks`. An admin key can list, create, and revoke sandbox keys. New-key secrets are returned only on create; list responses contain metadata only. Permissions are `sandbox:read`, `sandbox:write`, `sandbox:webhooks`, and `sandbox:admin`.

```bash
curl "$SANDBOX_BASE_URL/api/v1/sandbox/account/api-keys" -H "X-API-Key: $SANDBOX_API_KEY"
```

## Webhook simulation

Create a webhook subscription:

```bash
curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/webhooks" \
  -H "X-API-Key: $SANDBOX_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Local test receiver","endpoint_url":"http://127.0.0.1:9000/webhooks/finpilot","event_types":["customer.created","verification.completed"]}'
```

Create a synthetic event payload (replace IDs):

```bash
curl -X POST "$SANDBOX_BASE_URL/api/v1/sandbox/webhooks/WEBHOOK_ID/simulate" \
  -H "X-API-Key: $SANDBOX_API_KEY" -H 'Content-Type: application/json' \
  -d '{"event_type":"customer.created","customer_id":"CUSTOMER_ID"}'
```

The API returns a stored payload with `delivery_status=SIMULATED_NOT_SENT`. The sandbox intentionally does **not** issue outbound HTTP requests to supplied endpoint URLs; use the payload to test your receiver safely. Subscribed events are also recorded for synthetic customer creation and mock verification.

## Isolation and lifecycle

- Each key grants access to one sandbox account only; all repository queries include that account ID.
- Data uses sandbox-only model and table names. The router never calls production customer repositories, production API-key verification, or real verification/webhook providers.
- Expired accounts (30 days after creation) are rejected. Set up an operational retention job to delete expired sandbox accounts according to your policy.
- Sandbox is disabled by default. Deploy to a distinct host/process with a different database, database credentials, secrets, storage directory and any queues from production. The same codebase may be used, but do not enable it on the production deployment.
