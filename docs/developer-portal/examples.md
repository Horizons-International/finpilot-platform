# API examples

Replace the base URL and placeholder credentials/UUIDs with values from your own sandbox tenant. Do not use production PII in test requests.

## Check deployment health

```bash
curl "$BASE_URL/health" -H "Accept: application/json"
```

## Sign in

```bash
curl -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"developer@example.com","password":"YOUR_PASSWORD"}'
```

Copy `data.access_token` from the response into `$ACCESS_TOKEN` for the next user-authenticated requests.

## Create a customer using a JWT

```bash
curl -X POST "$BASE_URL/api/v1/customers" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name":"Amina",
    "last_name":"Example",
    "email":"amina@example.com",
    "phone_number":"+12025550123",
    "status":"NEW"
  }'
```

This request requires an authorized user role and must conform to the current `CustomerCreate` schema. Consult `/docs` for required fields, validation rules, and supported enum values for the deployed release.

## Read partner customer data using an API key

```bash
curl "$BASE_URL/api/v1/integrations/customers?limit=25" \
  -H "X-API-Key: $FINPILOT_API_KEY" \
  -H "Accept: application/json"
```

The key must be active and include `customers:read`. Data returned by this route is limited to the key's tenant.

## List verification cases for a customer

```bash
curl "$BASE_URL/api/v1/customers/$CUSTOMER_ID/verification-cases" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json"
```

## Read the latest risk prediction

```bash
curl "$BASE_URL/api/v1/customers/$CUSTOMER_ID/risk-predictions/latest" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json"
```

## Register a webhook

```bash
curl -X POST "$BASE_URL/api/v1/webhooks" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "endpoint_url":"https://partner.example.com/finpilot/events",
    "event_types":["customer.created","customer.updated"]
  }'
```

The response returns the webhook metadata and a one-time signing secret. Save the signing secret securely. Only public HTTPS callback endpoints are accepted, and event types must be in the API's supported event list.
