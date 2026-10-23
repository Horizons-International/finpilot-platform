# FinPilot Enterprise Deployment Framework

This directory contains the deployment configuration, scripts, and environment templates for FinPilot.

The framework adds automated container builds, deployment to separate environments, release tracking, deployment verification, and application rollback to the existing FinPilot application.

It integrates with the current FastAPI backend, Docker, Docker Compose, Alembic, GitHub Actions, and GitHub Container Registry (GHCR).

For local development and deployment testing, the Ubuntu machine on which the GitHub Actions self-hosted runner operates can also serve as the deployment host. A cloud server is not required for this setup.

## 1. Deployment architecture

The automated deployment process is:

```text
Developer
    |
    v
GitHub feature branch
    |
    v
Pull request
    |
    v
Automated quality checks and tests
    |
    v
Merge or version tag
    |
    v
Docker image build and publication to GHCR
    |
    v
Self-hosted Ubuntu runner
    |
    v
SSH deployment to the configured Ubuntu host
    |
    v
Database migrations
    |
    v
Application rollout and health verification
    |
    v
Release tracking
```

The workflows are defined in:

- `.github/workflows/deployment-pipeline.yml`
- `.github/workflows/deploy-release.yml`

The existing CI workflows remain separate.

### Deployment triggers

| Trigger | Result | Target environment |
|---|---|---|
| Pull request to `develop`, `main`, or `master` | Quality checks and tests | No deployment |
| Push to `develop` | Build, publish, and deploy | Development |
| Push to `main` or `master` | Build, publish, and deploy | Testing |
| Push a matching `v*.*.*` version tag | Build, publish, and deploy after environment protection permits | Production |
| Manually run `Deploy Existing FinPilot Release` | Verify and deploy an already-published image | Selected environment |

Staging is available through the manual release workflow.

The manual release workflow accepts these environment names:

- `development`
- `testing`
- `staging`
- `production`

A pull request passing its checks does not automatically deploy the application. The deployment pipeline is triggered separately by a qualifying push or version tag.

Production approval must be configured through the GitHub `production` Environment. Staging approval can also be configured through its GitHub Environment.

A configured environment name alone does not enforce approval. Reviewers and applicable protection rules must be enabled where supported by the repository's GitHub plan.

## 2. Single-Ubuntu-machine setup

The local Ubuntu machine can serve as both the self-hosted runner and the deployment target.

The Windows installation is used for development, editing, committing, and pushing changes. Ubuntu must be running when the deployment workflow needs the self-hosted runner.

The deployment job uses the following GitHub Actions runner labels:

```yaml
runs-on: [self-hosted, linux, x64]
```

The build and publication jobs use GitHub-hosted Ubuntu runners. The deployment job runs on the local self-hosted runner and connects to the configured deployment host over SSH.

For deployment to the same Ubuntu machine, configure the following values in each GitHub Environment:

```text
DEPLOY_HOST=127.0.0.1
DEPLOY_USER=finpilot-deploy
```

The actual values are entered through GitHub Environment secrets and variables; they must not be committed to the repository.

Required host components:

- Ubuntu Linux.
- OpenSSH server.
- Docker Engine and Docker Compose v2.
- A deployment account that can execute Docker commands.
- A registered and online GitHub Actions self-hosted runner.
- SSH key authentication between the runner account and the deployment account.
- Access to the required GHCR container image and PostgreSQL database.

Keep the Ubuntu machine powered on, awake, and connected to the internet when deployment jobs are expected.

A dual-boot PC is suitable for development and deployment testing. It is not, by itself, a reliable production high-availability platform. Running three API containers behind HAProxy on one computer provides multiple application instances, but does not protect against failure of the host itself.

## 3. Environment separation

FinPilot supports four environments:

- Development
- Testing
- Staging
- Production

Each environment must have its own runtime configuration, database and credentials, application secrets, and persistent storage.

The environment templates are stored in:

```text
deploy/environments/
    development.env.example
    testing.env.example
    staging.env.example
    production.env.example
```

These are templates, not production-ready runtime configuration files.

### Recommended deployment paths for one Ubuntu machine

The deployment scripts store release-state markers under:

```text
${DEPLOY_PATH}/.deploy-state/
```

The current scripts do not add the environment name to that state directory. Therefore, when multiple environments run on the same machine, configure a distinct `DEPLOY_PATH` for each environment. Otherwise, their rollback markers can conflict.

Use the following deployment roots:

| Environment | GitHub Environment variable `DEPLOY_PATH` |
|---|---|
| Development | `/opt/finpilot/deployment/development` |
| Testing | `/opt/finpilot/deployment/testing` |
| Staging | `/opt/finpilot/deployment/staging` |
| Production | `/opt/finpilot/deployment/production` |

With these values, the runtime configuration files must exist at the following paths:

```text
/opt/finpilot/deployment/development/development.env
/opt/finpilot/deployment/testing/testing.env
/opt/finpilot/deployment/staging/staging.env
/opt/finpilot/deployment/production/production.env
```

The deployment workflow uploads the Compose configuration and deployment scripts to the selected deployment root. It does not upload the runtime environment file.

Provision the runtime environment files separately on Ubuntu. Start with the corresponding example file, replace every placeholder with an appropriate value, and restrict access to the real file.

For example, if the development deployment root is `/opt/finpilot/deployment/development`, the development runtime file must be:

```text
/opt/finpilot/deployment/development/development.env
```

Restrict runtime file permissions:

```bash
chmod 600 /opt/finpilot/deployment/development/development.env
```

Use the equivalent path for each additional environment.

Do not commit real `.env` files, passwords, signing keys, encryption keys, or provider credentials.

The `RUNTIME_ENV_FILE` setting present in the example templates should be kept consistent with the corresponding runtime path if that variable is retained in the configuration. The deployment script itself determines the runtime file path from `DEPLOY_PATH` and the selected environment.

### Compose projects and port assignments

The release Compose configuration creates separate Compose projects and environment-specific named storage volumes. The deployment script supplies the environment name and storage volume when deploying.

The example environment templates assign separate host ports:

| Environment | HTTP/API port | HAProxy statistics port |
|---|---:|---:|
| Development | 8101 | 8411 |
| Testing | 8102 | 8412 |
| Staging | 8103 | 8413 |
| Production | 8104 | 8414 |

The HAProxy configuration listens on container port `8080` for HTTP and `8404` for statistics. The host ports listed above map to those container ports.

The Compose file binds these ports to `127.0.0.1`. Consequently, they are available from the Ubuntu machine itself but are not directly exposed to other computers on the network.

To expose the application externally, use an approved reverse proxy or ingress that terminates HTTPS and restricts access appropriately.

The example port values must remain unique if the four environments run simultaneously on the same host.

## 4. Database requirements

The release Compose stack does not provision PostgreSQL. A PostgreSQL database must exist separately and be reachable from the application containers.

FinPilot requires the database configuration and extensions required by the current application, including pgvector where applicable.

Use distinct databases and database credentials for each environment. For example:

```text
finpilot_development
finpilot_testing
finpilot_staging
finpilot_production
```

These are suggested names; the actual database names are determined by the runtime configuration.

Each runtime environment file must contain a valid `DATABASE_URL` pointing to the correct database.

Important requirements:

- Do not use the production database for testing or staging.
- Do not reuse production database credentials in other environments.
- Use synthetic or appropriately authorized non-production data.
- Configure TLS and certificate verification for staging and production database connections.
- Ensure that the database endpoint is reachable from the application container network. `localhost` inside a container refers to that container, not automatically to Ubuntu's host.
- Confirm that database backups and recovery procedures are available before making high-risk production schema changes.

The example templates contain placeholders and must be configured before deployment.

## 5. GitHub Environments and required configuration

Create these GitHub Environments in the repository:

```text
development
testing
staging
production
```

Each deployment job selects one of these environments, which determines its environment-specific secrets and variables.

### Required environment variable

Configure this variable in each environment:

| Variable | Purpose |
|---|---|
| `DEPLOY_PATH` | Absolute deployment root on the target host |

Use the environment-specific paths listed in Section 3.

### Required environment secrets

Configure the following secrets in each GitHub Environment, using the exact names referenced by the workflows.

| Secret | Purpose |
|---|---|
| `DEPLOY_HOST` | Target host DNS name or IP address |
| `DEPLOY_USER` | SSH deployment account |
| `DEPLOY_SSH_PRIVATE_KEY` | Private SSH key used by the deployment job |
| `DEPLOY_SSH_KNOWN_HOSTS` | Verified SSH host-key entry for the target |
| `GHCR_USERNAME` | Identity authorized to pull the container image |
| `GHCR_PULL_TOKEN` | Token with read access to the required GHCR package |

For deployment to the same Ubuntu machine, `DEPLOY_HOST` can be `127.0.0.1`, provided SSH listens on that address and the SSH host-key entry matches the connection destination.

Verify the SSH host fingerprint through a trusted channel. Do not blindly trust a newly generated `ssh-keyscan` output.

The image-building job uses GitHub's automatically supplied `GITHUB_TOKEN` to publish the image to GHCR. The deployment host separately authenticates to GHCR with its configured pull credentials.

Grant only the permissions needed by each credential. Protect the deployment account, private SSH keys, and Docker access as privileged resources.

The runtime configuration files are provisioned separately on the deployment host. They are not uploaded by the workflow.

## 6. Container image build and version management

The pipeline builds the application Docker image using the repository's root build context and `docker/Dockerfile`.

Images are published to:

```text
ghcr.io/horizons-international/finpilot-platform
```

The pipeline generates an immutable commit-SHA tag for each successful image build and also generates a version tag when the source is a matching version tag.

The release manifest is uploaded as a workflow artifact with a name similar to:

```text
release-manifest-<commit-sha>
```

It records the source repository, commit, reference, image, and workflow run information.

Use the full commit-SHA tag or a published version tag for deployments and promotions. Do not use movable tags such as `latest` or `stable` for releases.

The successful image build is a prerequisite for the automatic deployment job. A failed verification or image publication prevents the dependent deployment job from running.

## 7. First-time deployment

Before the first deployment:

1. Confirm that the self-hosted runner is online and matches the workflow's runner labels.
2. Confirm that SSH key authentication from the runner account to the deployment account works.
3. Confirm that Docker and Docker Compose are available to the deployment account.
4. Create the environment-specific deployment root and runtime configuration file.
5. Configure the correct database URL, credentials, secrets, and host port values.
6. Ensure that the host can pull the FinPilot image from GHCR.
7. Configure the GitHub Environment variables and secrets.
8. Merge the workflows into the default branch and confirm that the required CI checks pass.

For the initial test, deploy to development or testing rather than production.

A successful push to `develop` triggers the automatic development deployment. A successful push to `main` or `master` triggers the automatic testing deployment.

To promote an already-published image to staging or to perform an explicit redeployment, run:

```text
.github/workflows/deploy-release.yml
```

Select the intended environment and enter the exact published commit-SHA or version tag.

The manual workflow first verifies that the requested image can be pulled from GHCR. The deployment job then runs under the selected GitHub Environment.

## 8. Application deployment and health verification

The remote deployment script:

1. Validates the target environment, release tag, and deployment path.
2. Confirms that the runtime environment file and deployment configuration exist.
3. Validates the Docker Compose configuration.
4. Pulls the requested image and HAProxy image.
5. Runs the forward Alembic migration command.
6. Updates the three backend services one at a time, checking health after each update.
7. Starts or updates HAProxy and the worker services.
8. Checks API readiness through HAProxy.
9. Records the last known-good release after verification succeeds.

The readiness check uses `/ready` through the HAProxy host port configured for the environment.

If readiness validation fails, the deployment fails and the last known-good release marker is not advanced. Inspect the container status, logs, configuration, database connectivity, and readiness endpoint before attempting recovery.

A successful deployment verifies that the configured commands completed and that the expected containers passed the scripted health checks. It does not, on its own, prove production capacity, regulatory compliance, or independent security certification.

## 9. Rollback

Deployment state is maintained under:

```text
${DEPLOY_PATH}/.deploy-state/
```

The scripts use these markers:

- `.last-good-release`: most recently verified release.
- `.previous-release`: release recorded before the latest rollout.
- `.in-progress-release`: indicates a rollout started but has not completed successfully.

Because each environment uses its own `DEPLOY_PATH`, its release markers remain separate from those of other environments.

### Rollback procedure

1. Stop further deployments to the affected environment.
2. Record the failed workflow run, release tag, logs, and health status.
3. Connect to the Ubuntu deployment host as the deployment account.
4. Set the correct environment-specific values and execute that environment's rollback script.
5. Confirm that the intended previously published image is restored.
6. Recheck container health, `/ready`, `/health`, critical API operations, worker logs, and database compatibility.
7. Record the rollback and its reason in the release/change record.

For example, the following command is for a deployment root configured as `/opt/finpilot/deployment/testing`:

```bash
FINPILOT_IMAGE=ghcr.io/horizons-international/finpilot-platform \
FINPILOT_ENVIRONMENT=testing \
FINPILOT_RUNTIME_ENV_FILE=/opt/finpilot/deployment/testing/testing.env \
FINPILOT_STORAGE_VOLUME=finpilot_testing_storage \
DEPLOY_PATH=/opt/finpilot/deployment/testing \
bash /opt/finpilot/deployment/testing/deploy/scripts/rollback-release.sh
```

Run it as the deployment account that has Docker permissions. The command above assumes that a previous known-good release has already been recorded.

The rollback script uses the previous release after a successful rollout, or the last known-good release when the in-progress marker indicates an interrupted rollout. An explicit published tag may be supplied as the first argument when necessary.

**Database schemas are not automatically downgraded.** The rollback operation redeploys an application image and reruns the forward migration command. Migrations should follow an expand/contract compatibility strategy so that the previous application version remains compatible with the current schema.

If a migration is not backward-compatible, or data integrity is in question, application rollback alone is insufficient. Follow the approved database backup and recovery procedure rather than automatically restoring a database.

Do not delete the previous release image or its required deployment state before confirming that rollback is available.

## 10. Database migration strategy

The deployment process runs:

```bash
uv run alembic upgrade head
```

using the new image before rolling out the backend containers.

Database changes must be backward-compatible with the currently running application version.

Prefer the following sequence:

1. Expand the schema in a backward-compatible way.
2. Deploy code that supports the old and new schema.
3. Backfill or migrate data when required.
4. Verify application behavior.
5. Remove the old schema only in a later release after confirming that no deployed code depends on it.

Test migrations against a restored non-production snapshot. Take and verify backups before high-risk production schema changes, following the organization's change and recovery procedures.

## 11. Operational limitations

This framework automates deployment; it does not provision all production infrastructure.

The framework does not automatically provision:

- DNS and TLS certificates.
- External PostgreSQL infrastructure.
- Firewalls or network ingress.
- Host monitoring and alerting.
- Backup scheduling and recovery validation.
- A centralized secret manager.
- Multiple independent production hosts.

The three backend instances and the worker services share the runtime configuration and environment-specific storage volume for their Compose project. Do not share a writable storage volume between environments unless that arrangement has been explicitly designed and tested.

A local Ubuntu machine is appropriate for demonstrating the release pipeline, verifying configuration separation, and testing rollback. Production operation for enterprise banking customers requires independently designed availability, security, monitoring, backup, network, and operational controls.

## 12. Definition of done

The deployment framework should not be considered complete merely because workflow files exist.

Verify the following:

- [ ] Pull requests run the intended quality gates and automated tests.
- [ ] The Docker image builds and is published to GHCR.
- [ ] Development and testing can deploy automatically from their configured branches.
- [ ] Staging and production can deploy a verified, previously published release.
- [ ] Runtime configuration and credentials are separated across the four environments.
- [ ] The intended production approval mechanism is configured and tested where supported.
- [ ] A deployed version can be traced to its commit, image tag, and workflow run.
- [ ] A non-production deployment completes successfully and passes its health checks.
- [ ] Rollback restores a previously known-good application version.
- [ ] Database migration and recovery limitations are documented.
- [ ] Deployment results and release evidence are retained for operational review.

Refer to `docs/deployment/DEPLOYMENT_RUNBOOK.md` for the operational release flow, migration strategy, release evidence, and recovery checklist.