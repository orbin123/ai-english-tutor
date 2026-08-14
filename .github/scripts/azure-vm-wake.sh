#!/usr/bin/env bash

# Runs as root through Azure VM Run Command after the VM reaches running. Sleep
# deliberately stops the container, so wake restarts it, verifies local health,
# and only then removes the Caddy maintenance marker.

set -Eeuo pipefail

readonly STATE_DIR="/var/lib/lingosai"
readonly MAINTENANCE_FILE="$STATE_DIR/maintenance"
readonly CONTAINER_NAME="lingosai-backend"

command -v curl >/dev/null 2>&1
command -v docker >/dev/null 2>&1
docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1

if [[ "$(docker container inspect --format '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]]; then
  docker start "$CONTAINER_NAME" >/dev/null
fi

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
    rm -f "$MAINTENANCE_FILE"
    printf 'Application container is locally live and ready.\n'
    exit 0
  fi
  printf 'Local wake health attempt %d/30 failed.\n' "$attempt"
  sleep 4
done

printf 'Application did not become healthy; maintenance mode remains active.\n' >&2
exit 1
