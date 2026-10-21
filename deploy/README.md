# FinPilot Enterprise Deployment Framework

This add-on provides a release pipeline and a Docker Compose deployment target for Linux Docker hosts. It is designed around the current FinPilot FastAPI + `uv` + Alembic stack and three API instances behind HAProxy. It does not replace your existing `docker/docker-compose.yml` or `.github/workflows/main.yml`.

## Deployment model

- Pull requests: dependency-locked installation, Alembic migration validation, Ruff, Black, MyPy, and pytest.
- Push to `develop`: tested OCI image published to GHCR, then automatic deployment to the `development` GitHub Environment.
- Push to `main` / `master`: tested OCI image published to GHCR, then automatic deployment to the `testing` Environment.
- Push a `vMAJOR.MINOR.PATCH` tag: tested image is published with both its immutable commit-SHA tag and the version tag; production deployment begins only after the `production` GitHub Environment protection rules approve it.
- Staging and explicit redeployments: use `.github/workflows/deploy-release.yml` to deploy an already-published image tag. Configure GitHub environment reviewers to require approval.

The automatically deployed image is referenced by its full Git SHA (except a version-tag deployment, which uses the version tag). Avoid deploying mutable tags such as `latest`.

## Important prerequisites

1. A Linux deployment host for each environment with Docker Engine and Docker Compose v2.
2. Each environment has a reachable PostgreSQL database with pgvector extension as required by the app. This production Compose template intentionally does **not** run or publish PostgreSQL; set `DATABASE_URL` in the host's private runtime env file. Production/staging should use a managed or separately operated database with TLS.
3. Configure a host-specific runtime environment file on the remote host at `${DEPLOY_PATH}/development.env`, `testing.env`, `staging.env`, or `production.env`. It must contain all settings required by FinPilot (`DATABASE_URL`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and production data-protection settings). Start from the relevant `deploy/environments/*.env.example`, generate unique secrets, and **never commit actual environment files**.
4. The remote deploy user must be able to use Docker. Granting access to the Docker socket is effectively root-level access; apply the bank's host-access policy.
5. Create GitHub Environments named `development`, `testing`, `staging`, and `production`. Add per-environment secrets/variables described below. Add required reviewers (and prevent self-review where available) for staging and production. GitHub Environments enforce approval only when their protection rules are configured: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments.
6. GHCR image package access: provide an environment secret `GHCR_PULL_TOKEN` with package-read permission and `GHCR_USERNAME`. Prefer a dedicated machine identity/token, rotation, and minimum scope. Docker may persist registry credentials under the deploy account. Protect that account’s Docker configuration and use an approved credential helper where available; do not share its home directory or Docker socket with untrusted users.

## GitHub Environment variables and secrets

For each environment, configure these values on its GitHub Environment:

**Variables**
- `DEPLOY_PATH`: absolute remote path, e.g. `/opt/finpilot/deployment`. Use a path containing only letters, numbers, `/`, `.`, `_`, and `-`.

**Secrets**
- `DEPLOY_HOST`: target host DNS name or IP.
- `DEPLOY_USER`: SSH account on that host.
- `DEPLOY_SSH_PRIVATE_KEY`: private key for the deploy account.
- `DEPLOY_SSH_KNOWN_HOSTS`: verified host-key lines for the target. Obtain the key/fingerprint via a trusted channel; do not blindly trust a new `ssh-keyscan` result in CI.
- `GHCR_USERNAME`: identity allowed to pull this image.
- `GHCR_PULL_TOKEN`: token with read access to the FinPilot container package.

The remote runtime env file is provisioned out-of-band; CI never uploads it. Set permissions to owner-only (e.g. `chmod 600 /opt/finpilot/deployment/production.env`). Make sure files and volumes have backups and are owned by an approved ops account.

## First-time setup

1. Create the target host and externally managed PostgreSQL database; create the database and enable required extensions according to the existing FinPilot database procedure.
2. Provision a strong runtime env file from the examples. Production settings must use `ENVIRONMENT=production`, an HTTPS `PUBLIC_BASE_URL`, strong unique secrets, `DATABASE_REQUIRE_SSL=true`, a TLS-enabled `DATABASE_URL` (`sslmode=verify-full` preferred), and a valid `DATA_PROTECTION_KEY`. Keep actual values in a secret manager/secure host path.
3. Open/allow host port 8000 only from the trusted TLS ingress/reverse proxy or approved network; the Compose file binds HAProxy to `127.0.0.1:8000`. Terminate HTTPS at the approved ingress or add a managed TLS configuration in front of this loopback-only port. Port 8404 is bound to loopback for HAProxy stats.
4. Configure GitHub Environments and secrets/variables.
5. Merge the workflow and deployment bundle into the default branch, confirm required CI checks pass, then push `develop` to deploy development and `main` to deploy testing.
6. For staging/production, confirm the release tag or full SHA exists in GHCR and use the manual deploy workflow. For production, prefer a reviewed `vMAJOR.MINOR.PATCH` tag.

## Remote storage and API availability

The three backend services share a named Docker volume specific to the environment (`finpilot_<environment>_storage`). PostgreSQL is external to the Compose stack. HAProxy is the API entry point on loopback. Worker services start with the release and use the same image/runtime env/volume. Do not point two environments at the same writable file-storage volume unless explicitly designed and tested.

This is an operational template, not infrastructure provisioning. It does not provision DNS, certificates, firewalls, host monitoring, the database, backup jobs, or a secret manager.

## Rollback

The deploy script stores release markers in `${DEPLOY_PATH}/.deploy-state/`:
- `.last-good-release`: tag most recently verified healthy.
- `.previous-release`: prior release tag.
- `.in-progress-release`: present when a rollout has started but has not completed verification.

To roll back using the **same image repository and environment**, SSH into the deployment host and run (replace placeholders with the exact configured values):

```bash
FINPILOT_IMAGE=ghcr.io/horizons-international/finpilot-platform \
FINPILOT_ENVIRONMENT=production \
FINPILOT_RUNTIME_ENV_FILE=/opt/finpilot/deployment/production.env \
FINPILOT_STORAGE_VOLUME=finpilot_production_storage \
DEPLOY_PATH=/opt/finpilot/deployment \
bash /opt/finpilot/deployment/deploy/scripts/rollback-release.sh
```

Alternatively pass an explicit known-good published tag as the first argument. The rollback script rolls application containers/workers back to the image tag and reruns the forward-only migration command, which is normally a no-op if the database is already current. **It never downgrades the database schema automatically.** Code and migration changes must follow an expand/contract compatibility strategy; if a schema change is not backward-compatible, application rollback alone is unsafe. Restore a database only through the approved recovery procedure with a verified backup and explicit incident/change authorization.

If rollout fails part-way, `.last-good-release` remains the last release that passed checks, and `.in-progress-release` remains to signal intervention is needed. The rollback script selects the last-good tag during an interrupted rollout.

## What successful deployment proves

A successful run proves the configured CI checks passed for the image-building commit, the image could be pulled, Alembic upgrade command returned success, all three backend containers became healthy, the loopback HAProxy readiness check passed, and worker containers were started. It does not by itself prove production capacity, regulatory compliance, safe database rollback, or a successful independent penetration test.
