#!/usr/bin/env bash

# Shared plumbing for the local Azure lifecycle scripts. Sourced, never run.
#
# These scripts are deliberately thin. Every state transition is delegated to
# .github/scripts/azure-control-plane.sh, which is the same code the protected
# GitHub workflows run — so a local wake and a workflow wake cannot drift apart.
# What lives here is only the local part: making sure the CLI is pointed at the
# right subscription before anything moves.

set -Eeuo pipefail

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CONTROL_PLANE="$REPO_ROOT/.github/scripts/azure-control-plane.sh"

# Pinned so a script cannot act on the wrong subscription if the CLI's default
# context has been changed for other work.
readonly EXPECTED_SUBSCRIPTION="e231ab32-f4d4-4a1b-b96c-3cf279036ab7"
readonly RESOURCE_GROUP="rg-lingosai-prod"
readonly VM_NAME="vm-lingosai-prod"
readonly POSTGRES_SERVER="psql-lingosai-e231"
readonly ACTIVE_UNTIL_TAG="lingosai-active-until"
readonly API_ORIGIN="https://api.lingosai.com"

# Azure's free allowance for this VM size, per calendar month.
readonly FREE_VM_HOURS=750
readonly VM_HOURS_WARN_AT=600

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
warn() { printf '\033[33mWARNING:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_azure_cli() {
  command -v az >/dev/null 2>&1 || die "the Azure CLI is required (brew install azure-cli)"
  command -v python3 >/dev/null 2>&1 || die "python3 is required"

  local current
  current="$(az account show --query id --output tsv 2>/dev/null)" \
    || die "not signed in. Run: az login"

  if [[ "$current" != "$EXPECTED_SUBSCRIPTION" ]]; then
    die "the active subscription is $current, expected $EXPECTED_SUBSCRIPTION.
       Run: az account set --subscription $EXPECTED_SUBSCRIPTION"
  fi
}

# The control plane invokes the in-guest scripts by relative path
# (--scripts @.github/scripts/...), so it must run from the repository root.
run_control_plane() {
  [[ -x "$CONTROL_PLANE" ]] || die "missing or non-executable: $CONTROL_PLANE"
  (
    cd "$REPO_ROOT"
    AZURE_RESOURCE_GROUP="$RESOURCE_GROUP" \
      AZURE_VM_NAME="$VM_NAME" \
      AZURE_POSTGRES_SERVER="$POSTGRES_SERVER" \
      "$CONTROL_PLANE" "$@"
  )
}

vm_power_state() {
  az vm get-instance-view \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
    --output tsv \
    --only-show-errors 2>/dev/null || echo "unknown"
}

postgres_state() {
  az postgres flexible-server show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$POSTGRES_SERVER" \
    --query state \
    --output tsv \
    --only-show-errors 2>/dev/null || echo "unknown"
}

active_until() {
  az group show \
    --name "$RESOURCE_GROUP" \
    --query "tags.\"$ACTIVE_UNTIL_TAG\"" \
    --output tsv \
    --only-show-errors 2>/dev/null || echo ""
}

# Prints "<http-status> <seconds>" for the public readiness endpoint, or
# "000 0.00" when the host could not be reached at all.
probe_readiness() {
  curl \
    --silent \
    --output /dev/null \
    --max-time 10 \
    --write-out '%{http_code} %{time_total}' \
    "$API_ORIGIN/health/ready" 2>/dev/null || echo "000 0.00"
}
