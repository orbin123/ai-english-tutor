#!/usr/bin/env bash

# Idempotent Azure VM/PostgreSQL lifecycle operations for the PR 7 workflows.
# Authentication is deliberately owned by azure/login in the calling workflow;
# this script never accepts or reads a client secret.

set -Eeuo pipefail

readonly EXPECTED_RESOURCE_GROUP="rg-lingosai-prod"
readonly EXPECTED_VM_NAME="vm-lingosai-prod"
readonly ACTIVE_UNTIL_TAG="lingosai-active-until"
readonly POLL_SECONDS="${AZURE_POLL_SECONDS:-15}"
readonly MAX_POLLS="${AZURE_MAX_POLLS:-120}" # 30 minutes at the default interval

resource_group="${AZURE_RESOURCE_GROUP:-$EXPECTED_RESOURCE_GROUP}"
vm_name="${AZURE_VM_NAME:-$EXPECTED_VM_NAME}"
postgres_server="${AZURE_POSTGRES_SERVER:-}"

error() {
  printf '::error::%s\n' "$*" >&2
}

notice() {
  printf '::notice::%s\n' "$*"
}

require_config() {
  if [[ "$resource_group" != "$EXPECTED_RESOURCE_GROUP" ]]; then
    error "AZURE_RESOURCE_GROUP must be $EXPECTED_RESOURCE_GROUP"
    return 1
  fi
  if [[ "$vm_name" != "$EXPECTED_VM_NAME" ]]; then
    error "AZURE_VM_NAME must be $EXPECTED_VM_NAME"
    return 1
  fi
  if [[ ! "$postgres_server" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]]; then
    error "AZURE_POSTGRES_SERVER is missing or is not a valid server name"
    return 1
  fi
  if [[ ! "$POLL_SECONDS" =~ ^[1-9][0-9]*$ ]] || [[ ! "$MAX_POLLS" =~ ^[1-9][0-9]*$ ]]; then
    error "Azure polling bounds must be positive integers"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required for portable UTC live-window calculations"
    return 1
  fi
}

resource_group_id() {
  az group show \
    --name "$resource_group" \
    --query id \
    --output tsv \
    --only-show-errors
}

read_active_until() {
  az group show \
    --name "$resource_group" \
    --query "tags.\"$ACTIVE_UNTIL_TAG\"" \
    --output tsv \
    --only-show-errors
}

read_deployed_digest() {
  az group show \
    --name "$resource_group" \
    --query 'tags."lingosai-deployed-digest"' \
    --output tsv \
    --only-show-errors
}

set_active_until() {
  local value="$1"
  local group_id
  group_id="$(resource_group_id)"
  az tag update \
    --resource-id "$group_id" \
    --operation Merge \
    --tags "$ACTIVE_UNTIL_TAG=$value" \
    --output none \
    --only-show-errors
}

postgres_state() {
  az postgres flexible-server show \
    --resource-group "$resource_group" \
    --name "$postgres_server" \
    --query state \
    --output tsv \
    --only-show-errors
}

vm_power_state() {
  az vm get-instance-view \
    --resource-group "$resource_group" \
    --name "$vm_name" \
    --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
    --output tsv \
    --only-show-errors
}

wait_for_postgres() {
  local wanted="$1"
  local state=""
  local attempt

  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    state="$(postgres_state)"
    printf 'PostgreSQL state: %s (attempt %d/%d)\n' "$state" "$attempt" "$MAX_POLLS"
    if [[ "$state" == "$wanted" ]]; then
      return 0
    fi
    sleep "$POLL_SECONDS"
  done

  error "PostgreSQL did not reach $wanted; last state was ${state:-unknown}"
  return 1
}

wait_for_vm() {
  local wanted="$1"
  local state=""
  local attempt

  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    state="$(vm_power_state)"
    printf 'VM power state: %s (attempt %d/%d)\n' "$state" "$attempt" "$MAX_POLLS"
    if [[ "$state" == "$wanted" ]]; then
      return 0
    fi
    sleep "$POLL_SECONDS"
  done

  error "VM did not reach $wanted; last state was ${state:-unknown}"
  return 1
}

start_postgres() {
  local state
  state="$(postgres_state)"

  case "$state" in
    Ready)
      notice "PostgreSQL is already Ready"
      ;;
    Stopped)
      az postgres flexible-server start \
        --resource-group "$resource_group" \
        --name "$postgres_server" \
        --output none \
        --only-show-errors
      ;;
    Starting | Updating)
      notice "PostgreSQL is already transitioning ($state)"
      ;;
    Stopping)
      wait_for_postgres Stopped
      az postgres flexible-server start \
        --resource-group "$resource_group" \
        --name "$postgres_server" \
        --output none \
        --only-show-errors
      ;;
    *)
      error "PostgreSQL cannot be started safely from state: ${state:-unknown}"
      return 1
      ;;
  esac

  wait_for_postgres Ready
}

start_vm() {
  local state
  state="$(vm_power_state)"

  case "$state" in
    PowerState/running)
      notice "VM is already running"
      ;;
    PowerState/deallocated | PowerState/stopped)
      az vm start \
        --resource-group "$resource_group" \
        --name "$vm_name" \
        --output none \
        --only-show-errors
      ;;
    PowerState/starting)
      notice "VM is already starting"
      ;;
    PowerState/deallocating)
      wait_for_vm PowerState/deallocated
      az vm start \
        --resource-group "$resource_group" \
        --name "$vm_name" \
        --output none \
        --only-show-errors
      ;;
    PowerState/stopping)
      wait_for_vm PowerState/stopped
      az vm start \
        --resource-group "$resource_group" \
        --name "$vm_name" \
        --output none \
        --only-show-errors
      ;;
    *)
      error "VM cannot be started safely from state: ${state:-unknown}"
      return 1
      ;;
  esac

  wait_for_vm PowerState/running
}

deployment_is_recorded() {
  local digest
  digest="$(read_deployed_digest)"
  [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
}

resume_vm_application() {
  az vm run-command invoke \
    --resource-group "$resource_group" \
    --name "$vm_name" \
    --command-id RunShellScript \
    --scripts @.github/scripts/azure-vm-wake.sh \
    --output none \
    --only-show-errors
}

wake() {
  local active_hours="${1:-}"
  local active_until

  if [[ ! "$active_hours" =~ ^([1-9]|1[0-9]|2[0-4])$ ]]; then
    error "active_hours must be an integer from 1 through 24"
    return 1
  fi

  active_until="$(python3 - "$active_hours" <<'PY'
from datetime import datetime, timedelta, timezone
import sys

deadline = datetime.now(timezone.utc) + timedelta(hours=int(sys.argv[1]))
print(deadline.strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)"

  # Set the bounded window before starting compute so the watchdog cannot race
  # and stop an intentionally warming environment.
  set_active_until "$active_until"
  printf 'Active window ends at %s\n' "$active_until"

  start_postgres
  start_vm

  if deployment_is_recorded; then
    resume_vm_application
    printf 'deployment_recorded=true\n' >>"${GITHUB_OUTPUT:-/dev/null}"
  else
    notice "No deployed digest is recorded; compute is ready for the initial protected deployment"
    printf 'deployment_recorded=false\n' >>"${GITHUB_OUTPUT:-/dev/null}"
  fi
  printf 'active_until=%s\n' "$active_until" >>"${GITHUB_OUTPUT:-/dev/null}"
}

graceful_stop_vm_application() {
  local state
  state="$(vm_power_state)"
  if [[ "$state" != "PowerState/running" ]]; then
    notice "VM is not running; skipping in-guest application drain"
    return 0
  fi

  az vm run-command invoke \
    --resource-group "$resource_group" \
    --name "$vm_name" \
    --command-id RunShellScript \
    --scripts @.github/scripts/azure-vm-stop.sh \
    --output none \
    --only-show-errors
}

deallocate_vm() {
  local state
  state="$(vm_power_state)"

  if [[ "$state" == "PowerState/deallocated" ]]; then
    notice "VM is already deallocated"
  else
    # Deallocate is intentional: an in-guest shutdown can leave the VM allocated
    # and consuming compute hours.
    az vm deallocate \
      --resource-group "$resource_group" \
      --name "$vm_name" \
      --output none \
      --only-show-errors
  fi

  wait_for_vm PowerState/deallocated
}

stop_postgres() {
  local state
  state="$(postgres_state)"

  case "$state" in
    Stopped)
      notice "PostgreSQL is already Stopped"
      ;;
    Ready)
      az postgres flexible-server stop \
        --resource-group "$resource_group" \
        --name "$postgres_server" \
        --output none \
        --only-show-errors
      ;;
    Stopping)
      notice "PostgreSQL is already stopping"
      ;;
    Starting | Updating)
      wait_for_postgres Ready
      az postgres flexible-server stop \
        --resource-group "$resource_group" \
        --name "$postgres_server" \
        --output none \
        --only-show-errors
      ;;
    *)
      error "PostgreSQL cannot be stopped safely from state: ${state:-unknown}"
      return 1
      ;;
  esac

  wait_for_postgres Stopped
}

sleep_environment() {
  local failures=0
  local expired="1970-01-01T00:00:00Z"

  # Expire first so a partial failure is retried by the next watchdog run.
  set_active_until "$expired" || failures=1

  # Preserve the required shutdown order: drain/stop the application,
  # deallocate and verify the VM, then stop and verify PostgreSQL.
  graceful_stop_vm_application || failures=1
  deallocate_vm || failures=1
  stop_postgres || failures=1

  set_active_until "$expired" || failures=1

  if ((failures != 0)); then
    error "Sleep encountered an error; the watchdog will retry because the live window is expired"
    return 1
  fi

  notice "VM is deallocated and PostgreSQL is stopped"
}

live_window_is_active() {
  local active_until active_epoch now_epoch
  active_until="$(read_active_until)"

  if [[ -z "$active_until" || "$active_until" == "None" ]]; then
    return 1
  fi
  if ! active_epoch="$(python3 - "$active_until" <<'PY' 2>/dev/null
from datetime import datetime, timezone
import sys

value = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
print(int(value.timestamp()))
PY
)"; then
    error "The $ACTIVE_UNTIL_TAG tag is malformed; treating it as expired"
    return 1
  fi

  now_epoch="$(python3 - <<'PY'
from datetime import datetime, timezone

print(int(datetime.now(timezone.utc).timestamp()))
PY
)"
  ((active_epoch > now_epoch))
}

preflight() {
  local pg_state vm_state
  if ! live_window_is_active; then
    error "No active production window exists; run the protected Azure wake workflow first"
    return 1
  fi

  pg_state="$(postgres_state)"
  vm_state="$(vm_power_state)"
  if [[ "$pg_state" != "Ready" || "$vm_state" != "PowerState/running" ]]; then
    error "Production is not ready (PostgreSQL=$pg_state, VM=$vm_state)"
    return 1
  fi

  notice "Production live-window and compute preflight passed"
}

watchdog() {
  if live_window_is_active; then
    notice "Live window is still active; watchdog made no changes"
    return 0
  fi

  notice "Live window is absent or expired; enforcing the cold state"
  sleep_environment
}

main() {
  local command="${1:-}"
  require_config

  case "$command" in
    wake)
      wake "${2:-}"
      ;;
    sleep)
      sleep_environment
      ;;
    preflight)
      preflight
      ;;
    watchdog)
      watchdog
      ;;
    *)
      error "usage: $0 {wake <1-24>|sleep|preflight|watchdog}"
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
