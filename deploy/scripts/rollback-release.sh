#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_PATH:?Set DEPLOY_PATH}"
: "${FINPILOT_IMAGE:?Set FINPILOT_IMAGE}"
: "${FINPILOT_ENVIRONMENT:?Set FINPILOT_ENVIRONMENT}"
: "${FINPILOT_RUNTIME_ENV_FILE:?Set FINPILOT_RUNTIME_ENV_FILE}"
: "${FINPILOT_STORAGE_VOLUME:?Set FINPILOT_STORAGE_VOLUME}"
STATE_DIR="$DEPLOY_PATH/.deploy-state"
LAST_GOOD="$STATE_DIR/.last-good-release"
PREVIOUS="$STATE_DIR/.previous-release"
IN_PROGRESS="$STATE_DIR/.in-progress-release"

if [[ -n "${1:-}" ]]; then
  TARGET="$1"
elif [[ -f "$IN_PROGRESS" && -s "$LAST_GOOD" ]]; then
  # A rollout failed before the new image was recorded as last-good.
  TARGET="$(cat "$LAST_GOOD")"
elif [[ -s "$PREVIOUS" ]]; then
  TARGET="$(cat "$PREVIOUS")"
else
  echo "No previous release marker is available. Pass an explicit known-good image tag." >&2
  exit 2
fi

if [[ ! "$TARGET" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ || "${TARGET,,}" == "latest" || "${TARGET,,}" == "stable" ]]; then echo "Invalid rollback tag; use a commit SHA or version tag." >&2; exit 2; fi
CURRENT=""
if [[ -s "$LAST_GOOD" ]]; then CURRENT="$(cat "$LAST_GOOD")"; fi
if [[ -z "$CURRENT" ]]; then
  echo "No last-good deployment is recorded; first deployment cannot be automatically rolled back." >&2
  exit 2
fi
if [[ "$TARGET" == "$CURRENT" && ! -f "$IN_PROGRESS" ]]; then
  echo "Rollback tag is already the last-good release ($CURRENT). Pass an explicit older tag to override." >&2
  exit 2
fi
printf 'Rolling back environment %s to %s (current last-good marker: %s).\n' "$FINPILOT_ENVIRONMENT" "$TARGET" "$CURRENT"
exec bash "$DEPLOY_PATH/deploy/scripts/deploy-release.sh" "$TARGET"
