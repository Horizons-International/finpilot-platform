# Customer management

## Purpose

Customer management provides the core customer record used by onboarding, identity verification, documents, risk scoring, compliance and operational workflows. Customer records belong to a tenant and are accessed through the authenticated user's tenant scope.

## Implementation locations

- API routes: `backend/app/api/customers.py`
- Contacts and addresses: `backend/app/api/customer_contacts.py`, `backend/app/api/customer_addresses.py`
- Onboarding: `backend/app/api/customer_onboarding.py`
- Related customer history and audit routes/services under `backend/app/`
- Models, schemas, repositories and services under `backend/app/`
- Schema lifecycle: revisions under `backend/alembic/versions/`

See the [feature catalogue](FeatureCatalogue.md) and [architecture](Architecture.md) for the package map.

## API discovery

The customer router is part of the versioned API. Start the application and inspect the generated OpenAPI schema at `/docs` or `/openapi.json` for the exact operations, fields, pagination, response models and permissions exposed by the selected release.

Common customer actions include creating a customer, listing/searching tenant-visible customers, retrieving a customer, updating permitted customer data, and managing related contacts, addresses and onboarding records. The live schema takes precedence over older endpoint examples.

## Access and tenant boundaries

- Customer endpoints require authentication and use the authenticated user's tenant context.
- The client must not be able to select another tenant by supplying a tenant ID.
- Related contacts, addresses, documents, verification cases and history must remain associated with the same tenant-owned customer.
- Cross-tenant/platform reporting is a separate privileged operation and must not be inferred from ordinary customer access.
- UUIDs are identifiers, not access tokens. Verify authorization before returning a resource or nested child.

When evaluating customer management, test permitted access and denial for IDs belonging to another tenant. Include reads and mutations; list filters alone are insufficient.

## Suggested reviewer flow

1. Create or use a synthetic customer in the isolated local environment.
2. Retrieve it and confirm response data matches submitted fields.
3. Update a permitted field and confirm persisted state.
4. Create/list related contact and address records where those APIs are enabled.
5. Exercise onboarding/verification with mock providers.
6. Create two test tenants and verify that a user in one tenant cannot read or change the other's customer or child resources.
7. Check audit/history records for operations expected to be recorded.

Use the [backend setup guide](../backend/README.md) to create a local database and administrator. The live OpenAPI schema is authoritative for payloads and permissions.
