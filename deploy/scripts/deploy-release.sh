#!/usr/bin/env bash
set -Eeuo pipefail

TAG="${1:-${RELEASE_TAG:-}}"
: "${DEPLOY_PATH:?Set DEPLOY_PATH to the remote deployment root}"
: "${FINPILOT_IMAGE:?Set FINPILOT_IMAGE, for example ghcr.io/horizons-international/finpilot-platform}"
: "${FINPILOT_ENVIRONMENT:?Set FINPILOT_ENVIRONMENT}"
: "${FINPILOT_RUNTIME_ENV_FILE:?Set FINPILOT_RUNTIME_ENV_FILE to the private runtime env file}"
: "${FINPILOT_STORAGE_VOLUME:?Set FINPILOT_STORAGE_VOLUME}"

case "$FINPILOT_ENVIRONMENT" in development|testing|staging|production) ;; *) echo "Unsupported environment: $FINPILOT_ENVIRONMENT" >&2; exit 2 ;; esac
if [[ ! "$TAG" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ || "${TAG,,}" == "latest" || "${TAG,,}" == "stable" ]]; then
  echo "Invalid/empty release tag. Use a published immutable commit SHA or version tag (not latest/stable)." >&2
  exit 2
fi
if [[ ! "$FINPILOT_IMAGE" =~ ^ghcr\.io/[a-z0-9][a-z0-9._/-]*$ ]]; then
  echo "FINPILOT_IMAGE must be a lower-case ghcr.io image path." >&2
  exit 2
fi
if [[ ! "$DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]+$ || "$DEPLOY_PATH" == *"/../"* || "$DEPLOY_PATH" == */.. || "$DEPLOY_PATH" == *"/./"* || "$DEPLOY_PATH" == */. ]]; then
  echo "DEPLOY_PATH must be a safe absolute path with no spaces or parent traversal." >&2
  exit 2
fi
if [[ ! -f "$FINPILOT_RUNTIME_ENV_FILE" ]]; then
  echo "Runtime environment file missing: $FINPILOT_RUNTIME_ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$DEPLOY_PATH/deploy/compose/docker-compose.release.yml" || ! -f "$DEPLOY_PATH/deploy/compose/haproxy.cfg" ]]; then
  echo "Deployment compose/config files are missing under $DEPLOY_PATH/deploy/compose." >&2
  exit 2
fi
command -v docker >/dev/null 2>&1 || { echo "docker is required on the deployment host." >&2; exit 127; }
command -v curl >/dev/null 2>&1 || { echo "curl is required for the post-deploy readiness check." >&2; exit 127; }

chmod 600 "$FINPILOT_RUNTIME_ENV_FILE"
STATE_DIR="$DEPLOY_PATH/.deploy-state"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
CURRENT_TAG=""
if [[ -s "$STATE_DIR/.last-good-release" ]]; then
  CURRENT_TAG="$(cat "$STATE_DIR/.last-good-release")"
fi
if [[ -n "$CURRENT_TAG" ]]; then
  printf '%s\n' "$CURRENT_TAG" > "$STATE_DIR/.previous-release"
fi
printf '%s\n' "$TAG" > "$STATE_DIR/.in-progress-release"

export RELEASE_TAG="$TAG"
export COMPOSE_PROFILES=workers
COMPOSE=(docker compose --project-name "finpilot-$FINPILOT_ENVIRONMENT" --env-file "$FINPILOT_RUNTIME_ENV_FILE" --file "$DEPLOY_PATH/deploy/compose/docker-compose.release.yml" --profile workers)

printf 'Validating Compose config for %s release %s...\n' "$FINPILOT_ENVIRONMENT" "$TAG"
"${COMPOSE[@]}" config --quiet
printf 'Pulling image and HAProxy...\n'
"${COMPOSE[@]}" pull backend backend-2 backend-3 haproxy sla-monitor analytics-aggregator report-export-worker webhook-delivery-worker

printf 'Applying Alembic migrations (forward only)...\n'
"${COMPOSE[@]}" run --rm --no-deps backend uv run alembic upgrade head

wait_healthy() {
  local service="$1" container state deadline
  deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    container="$("${COMPOSE[@]}" ps -q "$service")"
    if [[ -n "$container" ]]; then
      state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
      if [[ "$state" == "healthy" ]]; then
        printf '%s is healthy.\n' "$service"
        return 0
      fi
      if [[ "$state" == "exited" || "$state" == "dead" ]]; then
        docker logs --tail 100 "$container" >&2 || true
        echo "$service entered state $state." >&2
        return 1
      fi
    fi
    sleep 3
  done
  container="$("${COMPOSE[@]}" ps -q "$service")"
  if [[ -n "$container" ]]; then docker logs --tail 100 "$container" >&2 || true; fi
  echo "Timed out waiting for $service health." >&2
  return 1
}

# Update one instance at a time so HAProxy can continue routing to healthy peers.
for service in backend backend-2 backend-3; do
  printf 'Rolling out %s...\n' "$service"
  "${COMPOSE[@]}" up -d --no-deps "$service"
  wait_healthy "$service"
done

printf 'Ensuring HAProxy is running...\n'
"${COMPOSE[@]}" up -d --no-deps haproxy

printf 'Updating worker services...\n'
"${COMPOSE[@]}" up -d --no-deps sla-monitor analytics-aggregator report-export-worker webhook-delivery-worker
sleep 3
for service in sla-monitor analytics-aggregator report-export-worker webhook-delivery-worker; do
  container="$("${COMPOSE[@]}" ps -q "$service")"
  if [[ -z "$container" ]]; then echo "Worker $service was not created." >&2; exit 1; fi
  state="$(docker inspect --format '{{.State.Status}}' "$container")"
  if [[ "$state" != "running" ]]; then
    docker logs --tail 100 "$container" >&2 || true
    echo "Worker $service is not running (state=$state)." >&2
    exit 1
  fi
done

printf 'Checking HAProxy readiness...\n'

# Discover the host port published for HAProxy's internal port 8000.
HTTP_BINDING="$("${COMPOSE[@]}" port haproxy 8080)"
HTTP_PORT="${HTTP_BINDING##*:}"

if [[ ! "$HTTP_PORT" =~ ^[0-9]+$ ]]; then
  echo "Could not determine HAProxy's published HTTP port: $HTTP_BINDING" >&2
  exit 1
fi

printf 'Checking API readiness at http://127.0.0.1:%s/ready\n' "$HTTP_PORT"

ready=0
for _ in $(seq 1 20); do
  if curl --fail --silent --show-error --max-time 5 \
      "http://127.0.0.1:${HTTP_PORT}/ready" >/dev/null; then
    ready=1
    break
  fi
  sleep 3
done
if [[ "$ready" -ne 1 ]]; then
  "${COMPOSE[@]}" ps >&2
  "${COMPOSE[@]}" logs --tail 100 haproxy backend backend-2 backend-3 >&2 || true
  echo "HAProxy/API readiness failed. .last-good-release remains unchanged; inspect the rollout, then run rollback-release.sh." >&2
  exit 1
fi

printf '%s\n' "$TAG" > "$STATE_DIR/.last-good-release"
rm -f "$STATE_DIR/.in-progress-release"
printf 'Deployment healthy: environment=%s tag=%s image=%s:%s\n' "$FINPILOT_ENVIRONMENT" "$FINPILOT_IMAGE" "$TAG" "$TAG"
printf 'Recorded last-good release in %s/.last-good-release\n' "$STATE_DIR"
