# Enterprise deployment runbook

## Release flow

```text
Developer change → Pull request → CI quality gates/tests → Merge or version tag
                 → Container image + release manifest → Environment deployment
                 → Migration → One-at-a-time API rollout → Readiness check
                 → Release markers + GitHub deployment history
```

The automation is defined in `.github/workflows/deployment-pipeline.yml` and `.github/workflows/deploy-release.yml`. Existing CI remains in place; these workflows add a self-contained release gate so the image being published depends on successful tests. A commit-SHA image tag provides immutable traceability. SemVer tags (`v1.2.3`) are additionally published and route to production after its environment protection rules approve the job.

## Trigger mapping

| Trigger | Result | Protection |
|---|---|---|
| Pull request to develop/main/master | Quality checks and tests only | No deploy secrets exposed |
| Push to develop | Build/publish and deploy to development | Configure development environment secrets |
| Push to main/master | Build/publish and deploy to testing | Configure testing environment secrets |
| Push a `vMAJOR.MINOR.PATCH` tag | Build/publish and prepare production deployment | Production Environment required reviewers must be configured |
| Manually run Deploy Existing FinPilot Release | Verify existing GHCR tag, then deploy selected environment | Selected GitHub Environment protection rules |

Only deploy a release tag emitted by a successful deployment-pipeline run. For a manual staging/production deployment, choose the full commit SHA or a published `vX.Y.Z` tag from a tested run. Do not type `latest` or another movable tag.

## Environment separation

Create four GitHub Environments: `development`, `testing`, `staging`, and `production`. Add `DEPLOY_PATH` as an environment variable and the six secrets described in `deploy/README.md`. Require reviewers for staging and production. On each Linux host, separately provision `<DEPLOY_PATH>/<environment>.env`; do not upload runtime configuration as a workflow artifact or commit it to Git.

Environment database, database role, signing/encryption keys, bootstrap credentials, external provider keys, storage volume, domain, and allowed ingress must be unique and appropriate for that environment. Use synthetic data outside authorized production processes. The Compose file exposes HAProxy only on loopback at ports 8000 and 8404; configure a trusted reverse proxy/ingress to terminate HTTPS and restrict access to these ports.

## Database migration strategy

The release script runs `uv run alembic upgrade head` using the newly published image before replacing API containers. Migrations must be backward-compatible with the currently running release: **expand → deploy compatible code → migrate/backfill → contract in a later release**. Do not add automatic Alembic downgrades to a deployment rollback. Test migrations against a restored non-production snapshot and take/verify a production database backup under the bank's change process before high-risk schema changes.

## Rollback procedure

1. Stop any further deployment and capture the failed workflow run ID, release tag, request IDs, logs, and health state.
2. SSH to the target host and use the command documented in `deploy/README.md`, running `deploy/scripts/rollback-release.sh`. During a partially completed rollout, the `.in-progress-release` marker causes rollback to select `.last-good-release`; after a successful rollout, it selects `.previous-release`.
3. Verify `/ready`, `/health`, login/critical workflows, worker logs, database compatibility, and expected service health. Record the rolled-back image and reason in the change/deployment record.
4. If the schema is not backward compatible or data integrity is in question, do not assume application rollback is enough. Execute the approved database restore/recovery plan with an explicit decision about data loss and RPO/RTO.

## Release tracking and evidence

Every pipeline build uploads `release-manifest-<commit SHA>` containing repository, commit, ref, image, and workflow run ID. GitHub Environment deployments record who/when approved and which workflow ran. On the host, `.deploy-state/.last-good-release` and `.previous-release` track the verified and prior tags. Link the workflow run, manifest artifact, migration result, health check, change ticket, approver, and rollback reference in the bank's release log.

## Operating checklist

- [ ] Change reviewed; all required CI checks passed for the exact source commit.
- [ ] Version/tag and image digest recorded; image came from GHCR published by CI.
- [ ] Migration reviewed for locking, duration, backward compatibility, and rollback implications.
- [ ] Backup/restore status and change window confirmed for high-risk changes.
- [ ] Environment-specific secrets/config/database/storage/ingress are confirmed.
- [ ] Staging and production approver accepted the deployment (as configured).
- [ ] Post-deploy readiness and smoke checks passed; logs/workers and critical workflows reviewed.
- [ ] Release manifest and evidence linked to change ticket; previous version and rollback path confirmed.
