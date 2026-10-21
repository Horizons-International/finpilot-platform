#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${DEPLOY_HOST:?Set DEPLOY_HOST secret}"
: "${DEPLOY_USER:?Set DEPLOY_USER secret}"
: "${DEPLOY_SSH_PRIVATE_KEY:?Set DEPLOY_SSH_PRIVATE_KEY secret}"
: "${DEPLOY_SSH_KNOWN_HOSTS:?Set DEPLOY_SSH_KNOWN_HOSTS secret}"
: "${DEPLOY_PATH:?Set DEPLOY_PATH environment variable}"
: "${GHCR_USERNAME:?Set GHCR_USERNAME secret}"
: "${GHCR_PULL_TOKEN:?Set GHCR_PULL_TOKEN secret}"
: "${FINPILOT_IMAGE:?Set FINPILOT_IMAGE}"
: "${RELEASE_TAG:?Set RELEASE_TAG}"
: "${TARGET_ENV:?Set TARGET_ENV}"

case "$TARGET_ENV" in development|testing|staging|production) ;; *) echo "Unsupported target environment: $TARGET_ENV" >&2; exit 2 ;; esac
if [[ ! "$RELEASE_TAG" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ || "${RELEASE_TAG,,}" == "latest" || "${RELEASE_TAG,,}" == "stable" ]]; then echo "Invalid release tag; use a commit SHA or version tag, not latest/stable." >&2; exit 2; fi
if [[ ! "$DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]+$ || "$DEPLOY_PATH" == *"/../"* || "$DEPLOY_PATH" == */.. || "$DEPLOY_PATH" == *"/./"* || "$DEPLOY_PATH" == */. ]]; then echo "DEPLOY_PATH must be a safe absolute remote path." >&2; exit 2; fi
if [[ ! "$GHCR_USERNAME" =~ ^[A-Za-z0-9-]+$ ]]; then echo "GHCR_USERNAME contains unsupported characters." >&2; exit 2; fi

command -v ssh >/dev/null || { echo "ssh is required on the runner." >&2; exit 127; }
command -v scp >/dev/null || { echo "scp is required on the runner." >&2; exit 127; }
# Use temporary storage so credentials are removed after this job.
umask 077

SSH_TEMP_DIR="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/finpilot-ssh.XXXXXX")"
trap 'rm -rf -- "$SSH_TEMP_DIR"' EXIT

KEY_FILE="$SSH_TEMP_DIR/deploy-key"
KNOWN_HOSTS_FILE="$SSH_TEMP_DIR/known-hosts"

printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" > "$KEY_FILE"
printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" > "$KNOWN_HOSTS_FILE"

chmod 600 "$KEY_FILE" "$KNOWN_HOSTS_FILE"

SSH_OPTS=(
  -i "$KEY_FILE"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE"
  -o ConnectTimeout=15
)
ENDPOINT="$DEPLOY_USER@$DEPLOY_HOST"

# Send the registry token over SSH stdin, not as a command-line argument.
printf '%s' "$GHCR_PULL_TOKEN" | ssh "${SSH_OPTS[@]}" "$ENDPOINT" "docker login ghcr.io --username '$GHCR_USERNAME' --password-stdin"
ssh "${SSH_OPTS[@]}" "$ENDPOINT" "mkdir -p '$DEPLOY_PATH/deploy/compose' '$DEPLOY_PATH/deploy/scripts'"
scp "${SSH_OPTS[@]}" "$ROOT/deploy/compose/docker-compose.release.yml" "$ROOT/deploy/compose/haproxy.cfg" "$ENDPOINT:$DEPLOY_PATH/deploy/compose/"
scp "${SSH_OPTS[@]}" "$ROOT/deploy/scripts/deploy-release.sh" "$ROOT/deploy/scripts/rollback-release.sh" "$ENDPOINT:$DEPLOY_PATH/deploy/scripts/"

RUNTIME_ENV_FILE="$DEPLOY_PATH/$TARGET_ENV.env"
STORAGE_VOLUME="finpilot_${TARGET_ENV}_storage"
REMOTE_COMMAND="FINPILOT_IMAGE='$FINPILOT_IMAGE' RELEASE_TAG='$RELEASE_TAG' FINPILOT_ENVIRONMENT='$TARGET_ENV' FINPILOT_RUNTIME_ENV_FILE='$RUNTIME_ENV_FILE' FINPILOT_STORAGE_VOLUME='$STORAGE_VOLUME' DEPLOY_PATH='$DEPLOY_PATH' bash '$DEPLOY_PATH/deploy/scripts/deploy-release.sh' '$RELEASE_TAG'"
ssh "${SSH_OPTS[@]}" "$ENDPOINT" "$REMOTE_COMMAND"
