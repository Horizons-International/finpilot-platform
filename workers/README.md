# Workers package placeholder

The background job modules are under **`backend/app/jobs/`**. The development Compose stack defines separate services for SLA monitoring, analytics aggregation, report exports and webhook delivery.

Inspect `docker/docker-compose.yml` and each job entry point before operating them. Do not start duplicate worker processes against one environment without checking concurrency/idempotency behavior.

See [architecture](../docs/Architecture.md), [backend setup](../backend/README.md) and [deployment](../deploy/README.md).
