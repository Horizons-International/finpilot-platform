# FinPilot high-availability foundation

## What the local stack provides

The development Compose configuration includes:
- Three API containers: `backend`, `backend-2`, `backend-3`.
- HAProxy as the local HTTP entry point on host port `8000`, with round-robin balancing and readiness checks against `/ready`.
- Per-container API health checks and PostgreSQL readiness using `pg_isready`.
- One shared PostgreSQL database service and named `finpilot_storage` volume used by all API instances.
- Prometheus and Blackbox Exporter probes for API instances, load-balanced readiness and PostgreSQL TCP reachability.
- HAProxy statistics on `http://127.0.0.1:8404/stats`; Prometheus on `http://127.0.0.1:9090`.

The existing `backend` service name remains available for developer commands, but client traffic should go through HAProxy on host port 8000.

## Run the current repository configuration

No overlay or ZIP copying is required; the Compose, HAProxy, monitoring and failover files are in this repository.

1. Review `docker/.env` privately. The current Git tree tracks a file at this path even though it should not be committed. Replace any real secrets with local-only secrets and remove it from Git before sharing; rotate potentially exposed credentials.
2. Validate the Compose file and monitoring configuration:

```powershell
docker compose -f docker/docker-compose.yml config
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
```

3. Apply pending migrations once, not concurrently from all API replicas:

```powershell
docker compose -f docker/docker-compose.yml exec backend uv run alembic upgrade head
```

4. Verify the local health endpoints:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1:8000/ready
```

5. Inspect Prometheus targets/alerts and HAProxy statistics in the browser.

## Simulate one API instance failure

From the repository root:

```powershell
.\tools\high_availability\test-failover.ps1
```

The script stops `backend-3`, checks that HAProxy continues to return readiness responses, and starts the container again in a cleanup path. It validates one API-container failure only. After an interrupted script, inspect Compose status and restart the stopped service if required.

## Limitations

- PostgreSQL remains one database instance; restart policy/readiness do not provide replication, automatic database failover or protection against disk/host loss.
- The API containers, HAProxy, PostgreSQL and named file-storage volume are all on one Docker host. This is not multi-host availability.
- The current security middleware rate limiter is process-local. Each API replica can have its own counters. Use a shared rate-limit service or trusted gateway/WAF before production.
- Prometheus rules are present, but this stack does not include Alertmanager or external notification delivery.
- The local named storage volume is not a distributed object store or multi-host shared file system.

For production, use independent failure domains, an HA PostgreSQL endpoint, highly available/shared object storage, external load balancing, centralized rate limiting, alert delivery, secure ingress/TLS, tested database and file recovery, and an on-call process.

## What success proves

A successful local failover script demonstrates that HAProxy can route around one stopped API container while the shared database and host remain available. It does not demonstrate database failover, host resilience, disaster recovery, or a production RTO/RPO guarantee.
