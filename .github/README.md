# GitHub automation

The workflows in this folder provide pull-request CI, deployment automation and dependency auditing.

| Workflow | Purpose |
|---|---|
| `main.yml` | Backend CI on pull requests to develop/main/master: pgvector PostgreSQL 17 service, locked uv install, Alembic migrations, Ruff, Black, MyPy and pytest |
| `deployment-pipeline.yml` | Validates deployment Compose on PRs; on qualifying pushes/tags it reruns quality gates, builds/publishes immutable GHCR images and deploys through a self-hosted Linux runner |
| `deploy-release.yml` | Manually verifies and deploys an already-published image into a selected environment |
| `security-audit.yml` | Exports the locked Python dependencies and runs pip-audit on PRs, main pushes, schedule and manual dispatch |

## Review requirements

- Inspect status checks on the exact commit/PR being reviewed.
- Configure self-hosted runner labels, GitHub Environments, environment variables and secrets before expecting a deployment workflow to deploy.
- Configure required reviewers/environment protection explicitly; naming an environment does not itself create an approval gate.
- Deployment workflows publish/reuse immutable commit SHA image tags. Do not assume a branch name or movable latest tag identifies an evaluated artifact.
- Keep secrets in GitHub Actions Environments/Secrets and the remote secret-management process. Never commit runtime .env files.

See [deployment documentation](../deploy/README.md) and the [deployment runbook](../docs/deployment/DEPLOYMENT_RUNBOOK.md).
