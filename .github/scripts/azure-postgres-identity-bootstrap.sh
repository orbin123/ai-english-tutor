#!/usr/bin/env bash

# Opens one exact temporary operator firewall rule, runs the credential-free
# Entra identity/database bootstrap, and removes the rule on every exit path.
# Arguments are non-secret identifiers; the database token stays in the Python
# process and comes only from the current Azure CLI login.

set -Eeuo pipefail
umask 077

readonly RESOURCE_GROUP="rg-lingosai-prod"
readonly FIREWALL_RULE="temporary-identity-bootstrap"
readonly SERVER_NAME="$1"
readonly ADMINISTRATOR_PRINCIPAL="$2"
readonly VM_OBJECT_ID="$3"
readonly OPERATOR_IPV4="$4"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
readonly REPO_ROOT

firewall_cleanup_required=0

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

delete_temporary_firewall_rule() {
  local original_status="$?"
  trap - EXIT

  if ((firewall_cleanup_required == 1)); then
    if az postgres flexible-server firewall-rule show \
      --resource-group "$RESOURCE_GROUP" \
      --server-name "$SERVER_NAME" \
      --name "$FIREWALL_RULE" \
      --output none \
      --only-show-errors >/dev/null 2>&1; then
      if ! az postgres flexible-server firewall-rule delete \
        --resource-group "$RESOURCE_GROUP" \
        --server-name "$SERVER_NAME" \
        --name "$FIREWALL_RULE" \
        --yes \
        --output none \
        --only-show-errors; then
        printf 'ERROR: failed to remove the temporary PostgreSQL firewall rule.\n' >&2
        exit 1
      fi
    fi

    if az postgres flexible-server firewall-rule show \
      --resource-group "$RESOURCE_GROUP" \
      --server-name "$SERVER_NAME" \
      --name "$FIREWALL_RULE" \
      --output none \
      --only-show-errors >/dev/null 2>&1; then
      printf 'ERROR: temporary PostgreSQL firewall rule still exists.\n' >&2
      exit 1
    fi
  fi

  exit "$original_status"
}

require_inputs() {
  [[ "$SERVER_NAME" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]] \
    || fail "invalid PostgreSQL server name"
  [[ "$ADMINISTRATOR_PRINCIPAL" =~ ^[^[:cntrl:]]{3,120}$ ]] \
    || fail "invalid Entra administrator principal name"
  [[ "$VM_OBJECT_ID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
    || fail "invalid VM managed-identity object ID"

  python3 - "$OPERATOR_IPV4" <<'PY'
from ipaddress import IPv4Address
import sys

try:
    address = IPv4Address(sys.argv[1])
except ValueError as exc:
    raise SystemExit("operator address must be one IPv4 address") from exc
if not address.is_global or str(address) in {"0.0.0.0", "255.255.255.255"}:
    raise SystemExit("operator address must be one public IPv4 address")
PY

  for tool in az python3 uv; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required"
  done
}

require_clean_server() {
  local state
  state="$(az postgres flexible-server show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$SERVER_NAME" \
    --query state \
    --output tsv \
    --only-show-errors)"
  [[ "$state" == "Ready" ]] || fail "PostgreSQL must be Ready; current state: $state"

  local rules_json
  rules_json="$(az postgres flexible-server firewall-rule list \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$SERVER_NAME" \
    --output json \
    --only-show-errors)"
  python3 -c '
import json
import sys

rules = json.load(sys.stdin)
if len(rules) != 1:
    raise SystemExit("expected exactly one PostgreSQL firewall rule")
rule = rules[0]
if rule.get("name") != "allow-vm-only":
    raise SystemExit("unexpected PostgreSQL firewall rule")
start = rule.get("startIpAddress")
end = rule.get("endIpAddress")
if start != end or start in {"0.0.0.0", "255.255.255.255", None}:
    raise SystemExit("the VM PostgreSQL firewall rule is not one exact IP")
' <<<"$rules_json"

  if az postgres flexible-server firewall-rule show \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$SERVER_NAME" \
    --name "$FIREWALL_RULE" \
    --output none \
    --only-show-errors >/dev/null 2>&1; then
    fail "the temporary PostgreSQL firewall rule already exists"
  fi
}

open_temporary_firewall_rule() {
  # Mark cleanup required before the create request so an interrupt cannot
  # strand a successfully created rule between the Azure response and a flag.
  firewall_cleanup_required=1
  az postgres flexible-server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$SERVER_NAME" \
    --name "$FIREWALL_RULE" \
    --start-ip-address "$OPERATOR_IPV4" \
    --end-ip-address "$OPERATOR_IPV4" \
    --output none \
    --only-show-errors
}

run_bootstrap() {
  (
    cd "$REPO_ROOT/backend"
    uv run python -m scripts.bootstrap_azure_postgres \
      --server-name "$SERVER_NAME" \
      --administrator-principal "$ADMINISTRATOR_PRINCIPAL" \
      --vm-object-id "$VM_OBJECT_ID"
  )
}

main() {
  require_inputs
  export AZURE_CORE_OUTPUT=none
  require_clean_server
  trap delete_temporary_firewall_rule EXIT
  open_temporary_firewall_rule
  run_bootstrap
  printf 'Azure PostgreSQL identity gate passed; closing operator access.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
