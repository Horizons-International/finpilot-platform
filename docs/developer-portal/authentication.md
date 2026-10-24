# Authentication guide

FinPilot currently has two separate authentication patterns. They are not interchangeable.

## 1. JWT for application endpoints

`POST /api/v1/auth/login` accepts a JSON body:

```json
{
  "email": "developer@example.com",
  "password": "YOUR_PASSWORD"
}
```

On success the standard API response envelope contains `data.access_token`, `data.refresh_token`, `data.token_type`, and user metadata. Use the access token, not the refresh token, for protected API calls:

```http
Authorization: Bearer <access_token>
```

Example:

```bash
export BASE_URL="https://your-sandbox.example.com"
export ACCESS_TOKEN="<token-from-login-response>"
curl "$BASE_URL/api/v1/customers?page=1&page_size=25" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json"
```

Access-token lifetime is configuration-controlled (default 30 minutes, maximum 60 minutes). The refresh route is `POST /api/v1/auth/refresh` with `{"refresh_token":"..."}`. A token must be active, unexpired, and associated with an active user/session according to the environment's policy. MFA-enabled accounts may need the optional `mfa_code` in the login request.

User endpoints enforce role/resource authorization in addition to token verification. A valid token does not grant every operation.

## 2. API keys for explicitly permissioned integrations

Create/list/revoke keys using the API-key administration routes; these routes require a user JWT and either Administrator or Organization Admin role.

- `POST /api/v1/api-keys` — create a key, passing `name` and `permissions`.
- `GET /api/v1/api-keys` — list the current tenant's key metadata.
- `POST /api/v1/api-keys/{api_key_id}/revoke` — revoke a key.
- `GET /api/v1/api-keys/{api_key_id}/usage?limit=100` — inspect recent usage.

Example create body:

```json
{
  "name": "Sandbox partner read integration",
  "permissions": ["customers:read"]
}
```

The key secret is returned only once under `data.api_key`. The database stores a hash, so the secret cannot be retrieved later. Copy it into a server-side secret manager immediately. Permissions must match `<resource>:<action>` syntax; provision only permissions that a route explicitly requires.

Send an API key with:

```http
X-API-Key: <api_key_secret>
```

API keys are not JWTs, do not create user sessions, and do not inherit user roles. The current partner read endpoint `GET /api/v1/integrations/customers` requires `customers:read`. Do not assume a route accepts API keys unless its documentation says so.

## Production checklist

- Use HTTPS.
- Keep passwords, JWTs, API keys, webhook signing secrets, and private data out of source control and logs.
- Use a separate, least-privilege key for each integration/environment.
- Rotate credentials after suspected disclosure and revoke unused keys.
- Never embed server credentials in public browser/mobile clients.
