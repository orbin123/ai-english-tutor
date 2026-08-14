#!/usr/bin/env bash

# Runs as root through Azure VM Run Command. It deploys only ACR images pinned
# by sha256 digest and authenticates the VM to ACR with its managed identity.
# Application secrets stay in the root-owned host environment file.

set -Eeuo pipefail
umask 077

readonly MODE="${1:-}"
readonly REQUESTED_IMAGE="${2:-}"
readonly REGISTRY_NAME="${3:-}"
readonly CONTAINER_NAME="lingosai-backend"
readonly IMAGE_REPOSITORY="lingosai-backend"
readonly STATE_DIR="/var/lib/lingosai"
readonly ENV_FILE="/etc/lingosai/backend.env"
readonly DEPLOYED_IMAGE_FILE="$STATE_DIR/deployed-image"
readonly ROLLBACK_IMAGE_FILE="$STATE_DIR/rollback-image"
readonly MAINTENANCE_FILE="$STATE_DIR/maintenance"
readonly ACR_TOKEN_USERNAME="00000000-0000-0000-0000-000000000000"

registry_host=""
previous_image=""
deployment_started=0

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

is_digest_reference() {
  local image="$1"
  [[ "$image" =~ ^[a-z0-9]+\.azurecr\.io/${IMAGE_REPOSITORY}@sha256:[a-f0-9]{64}$ ]]
}

require_host_contract() {
  local tool
  for tool in az curl docker; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required on the VM"
  done

  [[ "$REGISTRY_NAME" =~ ^[a-z0-9]{5,50}$ ]] || fail "invalid ACR name"
  registry_host="${REGISTRY_NAME}.azurecr.io"

  install -d -m 0755 "$STATE_DIR"
  [[ -f "$ENV_FILE" ]] || fail "$ENV_FILE is missing"
  [[ "$(stat -c '%U:%G' "$ENV_FILE")" == "root:root" ]] || fail "$ENV_FILE must be owned by root"
  local env_mode
  env_mode="$(stat -c '%a' "$ENV_FILE")"
  if ((8#$env_mode > 8#600)); then
    fail "$ENV_FILE must not be more permissive than mode 0600"
  fi
}

managed_identity_login() {
  export AZURE_CORE_OUTPUT=none
  az login --identity --output none --only-show-errors
}

clear_managed_identity_session() {
  az logout --output none >/dev/null 2>&1 || true
}

pull_image() {
  local image="$1"
  local token

  is_digest_reference "$image" || fail "refusing non-digest image reference"
  [[ "$image" == "$registry_host/"* ]] || fail "image registry does not match the approved ACR"

  token="$(az acr login \
    --name "$REGISTRY_NAME" \
    --expose-token \
    --query accessToken \
    --output tsv \
    --only-show-errors)"
  [[ -n "$token" ]] || fail "managed identity did not receive an ACR access token"
  printf '%s' "$token" | docker login \
    "$registry_host" \
    --username "$ACR_TOKEN_USERNAME" \
    --password-stdin >/dev/null
  unset token

  if ! docker pull "$image"; then
    docker logout "$registry_host" >/dev/null 2>&1 || true
    fail "failed to pull $image"
  fi
  docker logout "$registry_host" >/dev/null 2>&1 || true
}

read_recorded_image() {
  local path="$1"
  local image=""
  if [[ -f "$path" ]]; then
    image="$(tr -d '\r\n' <"$path")"
    if is_digest_reference "$image" && [[ "$image" == "$registry_host/"* ]]; then
      printf '%s' "$image"
    fi
  fi
}

current_container_image() {
  local image=""
  if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    image="$(docker container inspect --format '{{.Config.Image}}' "$CONTAINER_NAME")"
    if is_digest_reference "$image" && [[ "$image" == "$registry_host/"* ]]; then
      printf '%s' "$image"
    fi
  fi
}

stop_current_container() {
  if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    docker stop --time 45 "$CONTAINER_NAME" >/dev/null
    docker rm "$CONTAINER_NAME" >/dev/null
  fi
}

start_container() {
  local image="$1"
  docker run --detach \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network host \
    --env-file "$ENV_FILE" \
    --env WEB_CONCURRENCY=1 \
    --env PORT=8000 \
    --memory 768m \
    --memory-swap 1024m \
    --log-driver json-file \
    --log-opt max-size=10m \
    --log-opt max-file=3 \
    "$image" >/dev/null
}

wait_for_local_health() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl \
      --fail \
      --silent \
      --show-error \
      --max-time 5 \
      http://127.0.0.1:8000/health/live >/dev/null \
      && curl \
        --fail \
        --silent \
        --show-error \
        --max-time 5 \
        http://127.0.0.1:8000/health/ready >/dev/null; then
      return 0
    fi
    log "Local health attempt $attempt/30 failed"
    sleep 4
  done
  return 1
}

run_one_off() {
  local image="$1"
  shift
  docker run --rm \
    --network host \
    --env-file "$ENV_FILE" \
    --env WEB_CONCURRENCY=1 \
    "$image" "$@"
}

restore_previous_after_failure() {
  local original_status="$?"
  trap - ERR

  if ((deployment_started == 0)); then
    exit "$original_status"
  fi

  log "Deployment failed; attempting application rollback. Database migrations are not reverted."
  stop_current_container || log "Failed to remove the unhealthy container before rollback"

  if [[ -n "$previous_image" ]]; then
    if pull_image "$previous_image" && start_container "$previous_image" && wait_for_local_health; then
      printf '%s\n' "$previous_image" >"$DEPLOYED_IMAGE_FILE"
      rm -f "$MAINTENANCE_FILE"
      log "Previous application image restored: $previous_image"
    else
      log "Rollback failed; maintenance mode remains active."
    fi
  else
    log "No previous digest was recorded; maintenance mode remains active."
  fi

  exit "$original_status"
}

deploy() {
  is_digest_reference "$REQUESTED_IMAGE" || fail "deployment requires an ACR sha256 digest reference"
  [[ "$REQUESTED_IMAGE" == "$registry_host/"* ]] || fail "deployment image does not belong to the approved ACR"

  pull_image "$REQUESTED_IMAGE"

  previous_image="$(current_container_image)"
  if [[ -z "$previous_image" ]]; then
    previous_image="$(read_recorded_image "$DEPLOYED_IMAGE_FILE")"
  fi
  if [[ -n "$previous_image" && "$previous_image" != "$REQUESTED_IMAGE" ]]; then
    printf '%s\n' "$previous_image" >"$ROLLBACK_IMAGE_FILE"
  fi

  touch "$MAINTENANCE_FILE"
  deployment_started=1
  trap restore_previous_after_failure ERR

  stop_current_container

  # Migrations are forward-only. The old image is restored on application
  # failure, but schema changes are never reversed automatically.
  run_one_off "$REQUESTED_IMAGE" alembic upgrade head
  run_one_off "$REQUESTED_IMAGE" \
    sh -c 'python -m scripts.seed_curriculum && python -m scripts.seed_ielts_challenge && python -m scripts.seed_a2z_challenge'

  start_container "$REQUESTED_IMAGE"
  wait_for_local_health

  printf '%s\n' "$REQUESTED_IMAGE" >"$DEPLOYED_IMAGE_FILE"
  rm -f "$MAINTENANCE_FILE"
  trap - ERR
  log "Deployment healthy at digest: $REQUESTED_IMAGE"
}

rollback() {
  local rollback_image current_image
  rollback_image="$(read_recorded_image "$ROLLBACK_IMAGE_FILE")"
  [[ -n "$rollback_image" ]] || fail "no rollback digest is recorded"

  current_image="$(current_container_image)"
  if [[ -z "$current_image" ]]; then
    current_image="$(read_recorded_image "$DEPLOYED_IMAGE_FILE")"
  fi

  pull_image "$rollback_image"
  touch "$MAINTENANCE_FILE"
  stop_current_container
  start_container "$rollback_image"
  if ! wait_for_local_health; then
    fail "rollback image did not become healthy; maintenance mode remains active"
  fi

  printf '%s\n' "$rollback_image" >"$DEPLOYED_IMAGE_FILE"
  if [[ -n "$current_image" && "$current_image" != "$rollback_image" ]]; then
    printf '%s\n' "$current_image" >"$ROLLBACK_IMAGE_FILE"
  fi
  rm -f "$MAINTENANCE_FILE"
  log "Rollback healthy at digest: $rollback_image"
}

main() {
  require_host_contract
  managed_identity_login
  trap clear_managed_identity_session EXIT

  case "$MODE" in
    deploy)
      deploy
      ;;
    rollback)
      rollback
      ;;
    *)
      fail "usage: $0 {deploy <digest>|rollback <unused>} <acr-name>"
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
fi
