#!/usr/bin/env bash

# Fail-closed verification for the separately bootstrapped Azure VM. It checks
# the local host contract and proves managed-identity read access without ever
# printing the Key Vault secret or ACR access token.

set -Eeuo pipefail
umask 077

readonly EXPECTED_API_HOSTNAME="api.lingosai.com"
readonly API_HOSTNAME="${1:-}"
readonly KEY_VAULT_NAME="${2:-}"
readonly ENV_SECRET_NAME="${3:-}"
readonly REGISTRY_NAME="${4:-}"
readonly POSTGRES_SERVER="${5:-}"
readonly STATE_DIR="/var/lib/lingosai"
readonly ENV_FILE="/etc/lingosai/backend.env"
readonly MAINTENANCE_FILE="$STATE_DIR/maintenance"

acr_token=""

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  unset acr_token
  az logout --output none >/dev/null 2>&1 || true
}

require_inputs() {
  [[ "$(id -u)" == "0" ]] || fail "this script must run as root"
  [[ "$API_HOSTNAME" == "$EXPECTED_API_HOSTNAME" ]] \
    || fail "the reviewed API hostname is $EXPECTED_API_HOSTNAME"
  [[ "$KEY_VAULT_NAME" =~ ^[A-Za-z][A-Za-z0-9-]{1,22}[A-Za-z0-9]$ ]] \
    || fail "invalid Key Vault name"
  [[ "$ENV_SECRET_NAME" =~ ^[A-Za-z0-9-]{1,127}$ ]] \
    || fail "invalid Key Vault secret name"
  [[ "$REGISTRY_NAME" =~ ^[a-z0-9]{5,50}$ ]] \
    || fail "invalid ACR name"
  [[ "$POSTGRES_SERVER" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]] \
    || fail "invalid PostgreSQL server name"
}

verify_local_contract() {
  local tool
  for tool in az caddy curl docker jq; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is not installed"
  done

  systemctl is-enabled --quiet docker.service \
    || fail "Docker is not enabled"
  systemctl is-active --quiet docker.service \
    || fail "Docker is not active"
  systemctl is-enabled --quiet caddy.service \
    || fail "Caddy is not enabled"
  systemctl is-active --quiet caddy.service \
    || fail "Caddy is not active"

  [[ -f "$ENV_FILE" ]] || fail "$ENV_FILE is missing"
  [[ "$(stat -c '%U:%G' "$ENV_FILE")" == "root:root" ]] \
    || fail "$ENV_FILE must be root-owned"
  local env_mode
  env_mode="$(stat -c '%a' "$ENV_FILE")"
  ((8#$env_mode <= 8#600)) || fail "$ENV_FILE is more permissive than 0600"

  [[ -f "$MAINTENANCE_FILE" ]] \
    || fail "maintenance mode must remain active before initial deployment"
  swapon --show=NAME --noheadings | sed 's/^[[:space:]]*//' \
    | grep -Fxq /swapfile || fail "the bounded swapfile is not active"
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

  grep -Fq "$API_HOSTNAME {" /etc/caddy/Caddyfile \
    || fail "Caddy does not contain the reviewed API hostname"
  grep -Fq 'reverse_proxy 127.0.0.1:8000' /etc/caddy/Caddyfile \
    || fail "Caddy does not proxy to the local backend"
  grep -Fq 'max_size 5MB' /etc/caddy/Caddyfile \
    || fail "Caddy does not enforce the upload cap"
}

verify_managed_identity_access() {
  export AZURE_CORE_OUTPUT=none
  az login --identity --output none --only-show-errors

  local secret_id
  secret_id="$(az keyvault secret show \
    --vault-name "$KEY_VAULT_NAME" \
    --name "$ENV_SECRET_NAME" \
    --query id \
    --output tsv \
    --only-show-errors)"
  [[ "$secret_id" == https://"$KEY_VAULT_NAME".vault.azure.net/secrets/"$ENV_SECRET_NAME"/* ]] \
    || fail "managed identity could not read the approved Key Vault secret"
  unset secret_id

  acr_token="$(az acr login \
    --name "$REGISTRY_NAME" \
    --expose-token \
    --query accessToken \
    --output tsv \
    --only-show-errors)"
  [[ -n "$acr_token" ]] \
    || fail "managed identity could not obtain an ACR pull token"
  unset acr_token
}

verify_postgres_network_path() {
  local postgres_hostname="$POSTGRES_SERVER.postgres.database.azure.com"
  getent ahostsv4 "$postgres_hostname" >/dev/null \
    || fail "the PostgreSQL hostname does not resolve"
  timeout 10 bash -c "exec 3<>/dev/tcp/$postgres_hostname/5432" \
    || fail "the exact-IP PostgreSQL endpoint is not reachable on port 5432"
}

main() {
  require_inputs
  trap cleanup EXIT
  verify_local_contract
  verify_managed_identity_access
  verify_postgres_network_path
  printf 'Azure VM host contract verified; maintenance mode remains active.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
