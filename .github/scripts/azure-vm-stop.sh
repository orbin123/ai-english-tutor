#!/usr/bin/env bash

# Runs as root through Azure VM Run Command. The marker is consumed by the
# separately provisioned Caddy maintenance configuration.

set -Eeuo pipefail

readonly STATE_DIR="/var/lib/lingosai"
readonly MAINTENANCE_FILE="$STATE_DIR/maintenance"
readonly CONTAINER_NAME="lingosai-backend"

install -d -m 0755 "$STATE_DIR"
touch "$MAINTENANCE_FILE"

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker is unavailable; Azure deallocation must still continue.\n' >&2
  exit 1
fi

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  docker stop --time 45 "$CONTAINER_NAME" >/dev/null
  printf 'Application container stopped cleanly.\n'
else
  printf 'Application container is already absent.\n'
fi
