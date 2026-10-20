# FinPilot High Availability Foundation

## What this implements

The replacement `docker/docker-compose.yml` keeps the existing service names used by day-to-day development and adds a local HA foundation:

- Three API instances (`backend`, `backend-2`, `backend-3`) built from `docker/Dockerfile`.
- HAProxy as the single HTTP entry point on port `8000`, with round-robin balancing and a readiness check against `/ready`.
- Each API container has a Docker health check against `/ready`; PostgreSQL uses `pg_isready`; services use `restart: unless-stopped`.
- All API instances use the same PostgreSQL endpoint, the same environment configuration and the same named `finpilot_storage` volume.
- Prometheus and the Blackbox Exporter probe each API instance, the load-balanced readiness endpoint, and PostgreSQL TCP reachability.
- Prometheus availability alert rules identify a failing backend, less than two healthy backends, an unavailable load balancer, and an unreachable PostgreSQL port.
- HAProxy's read-only stats page is available on `http://127.0.0.1:8404/stats`; Prometheus is available on `http://127.0.0.1:9090`.

The existing `backend` service remains named `backend` so commands such as `docker compose exec backend uv run alembic upgrade head` continue to work. The `backend` service no longer publishes port 8000 directly; client traffic should go through HAProxy on host port 8000.

## Apply the files

1. Back up your current `docker/docker-compose.yml`.
2. Copy the ZIP's `docker/docker-compose.yml` over the existing file.
3. Copy the ZIP's `docker/haproxy/`, `docker/monitoring/`, and `tools/high_availability/` directories into the repository, preserving paths.
4. Check that `docker/.env` exists and has the same DATABASE_URL and secrets your current development stack needs.
5. From the repository root, run:

   ```powershell
   docker compose -f docker/docker-compose.yml config
   docker compose -f docker/docker-compose.yml run --rm --no-deps --entrypoint haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
   docker compose -f docker/docker-compose.yml run --rm --no-deps --entrypoint promtool prometheus check config /etc/prometheus/prometheus.yml
   docker compose -f docker/docker-compose.yml up -d --build
   docker compose -f docker/docker-compose.yml ps
   ```

6. Apply Alembic migrations using the existing workflow if code/database migrations are pending:

   ```powershell
   docker compose -f docker/docker-compose.yml exec backend uv run alembic upgrade head
   ```

   Do not run migrations concurrently from all API instances; run them once as an explicit deployment step.

7. Check readiness and monitor pages:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:8000/health
   Invoke-WebRequest http://127.0.0.1:8000/ready
   ```

   Open `http://127.0.0.1:9090/targets`, `http://127.0.0.1:9090/alerts`, and `http://127.0.0.1:8404/stats` in a browser.

## Test an instance failure

From the repository root, run the included PowerShell test. It stops only `backend-3`, waits for HAProxy to route around it, verifies repeated readiness requests, and starts `backend-3` again in a `finally` block:

```powershell
.\tools\high_availability\test-failover.ps1
```

If the script terminates unexpectedly, check `docker compose -f docker/docker-compose.yml ps` and run `docker compose -f docker/docker-compose.yml start backend-3` if needed. This test only covers one API container failure.

## Database availability strategy and limitations

The Compose PostgreSQL service now has readiness checks, dependency gating, a persistent volume, and `restart: unless-stopped`. **It remains one PostgreSQL instance and is a single point of failure.** These controls help it restart after a process/container fault but do not provide database-node redundancy, automatic database failover, or protection from host/disk loss.

For production, use a managed PostgreSQL HA service or a separately operated PostgreSQL cluster with synchronous/asynchronous replication, tested failover, backups, and a stable writer endpoint. Configure `DATABASE_URL` to that service's failover endpoint. Do not point multiple independent writable databases at the application or assume a backup volume is a replica. The local Compose file deliberately does not create a second database and does not automatically migrate or copy existing database data into a cluster.

Similarly, all local Compose services and the shared local storage volume are still on one Docker host. For host-level high availability, run replicas on separate hosts/availability zones behind an external load balancer, and replace the local named storage volume with highly available shared/object storage. A local HAProxy container cannot survive failure of its own host.

The current `SecurityMonitoringMiddleware` implements rate limiting in process-local memory. With multiple API instances, each instance has its own buckets. Before production traffic, enforce shared rate limiting at a gateway or add a supported shared-store implementation. Review all process-local caches/state for the same scaling concern.

Prometheus alert rules are visible in its Alerts UI, but this bundle does not include an Alertmanager or external notifications. Connect Alertmanager or your existing alerting platform before relying on these alerts operationally.

## Production hardening checklist

- Terminate HTTPS at an approved edge/load balancer and forward requests over a trusted network.
- Do not expose PostgreSQL, pgAdmin, Prometheus, or HAProxy stats publicly; restrict management ports and use strong, externally managed secrets.
- Replace the current development-only PostgreSQL and pgAdmin credentials before any production deployment.
- Run application replicas across different hosts or failure zones, not only as containers on one machine.
- Use an HA PostgreSQL writer endpoint and shared highly available file/object storage.
- Centralize rate limits and any other stateful request controls.
- Configure alert delivery, dashboards, logs, and a tested on-call runbook.
- Run the failover exercise and record results for backend failure, PostgreSQL failover, host failure, and load-balancer/edge failure separately.
- Measure actual recovery time and data loss; do not label RTO/RPO as guarantees until the tests substantiate them.

## What success proves

A successful local run demonstrates app-instance redundancy behind an HTTP load balancer, per-instance readiness monitoring, container restart policies, and visible availability probes. It does not prove multi-host high availability or database failover.
