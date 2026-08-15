#!/usr/bin/env bash

# Idempotently prepares the single Azure production VM. This script is sent
# through Azure VM Run Command, so every argument is a non-secret identifier.
# The application environment is read directly from Key Vault by the VM's
# system-assigned identity and is never returned to the caller.

set -Eeuo pipefail
umask 077

readonly EXPECTED_API_HOSTNAME="api.lingosai.com"
readonly API_HOSTNAME="${1:-}"
readonly KEY_VAULT_NAME="${2:-}"
readonly ENV_SECRET_NAME="${3:-}"
readonly STATE_DIR="/var/lib/lingosai"
readonly CONFIG_DIR="/etc/lingosai"
readonly ENV_FILE="$CONFIG_DIR/backend.env"
readonly MAINTENANCE_FILE="$STATE_DIR/maintenance"
readonly CADDY_KEYRING="/usr/share/keyrings/caddy-stable-archive-keyring.gpg"
readonly CADDY_SOURCE="/etc/apt/sources.list.d/caddy-stable.list"
readonly MICROSOFT_KEYRING="/etc/apt/keyrings/microsoft.gpg"
readonly MICROSOFT_SOURCE="/etc/apt/sources.list.d/azure-cli.list"

env_tmp=""

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$env_tmp" ]]; then
    rm -f -- "$env_tmp"
  fi
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
}

install_base_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install --yes \
    ca-certificates \
    curl \
    docker.io \
    gnupg \
    jq \
    unattended-upgrades
}

install_caddy() {
  if ! command -v caddy >/dev/null 2>&1; then
    curl --fail --silent --show-error --location \
      https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
      | gpg --dearmor --yes --output "$CADDY_KEYRING"
    curl --fail --silent --show-error --location \
      https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
      --output "$CADDY_SOURCE"
    apt-get update
    apt-get install --yes caddy
  fi

  local caddy_version
  caddy_version="$(caddy version | awk '{print $1}' | sed 's/^v//')"
  dpkg --compare-versions "$caddy_version" ge 2.10.0 \
    || fail "Caddy 2.10.0 or newer is required for request-size enforcement"
}

install_azure_cli() {
  if ! command -v az >/dev/null 2>&1; then
    install -d -m 0755 /etc/apt/keyrings
    curl --fail --silent --show-error --location \
      https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor --yes --output "$MICROSOFT_KEYRING"
    chmod 0644 "$MICROSOFT_KEYRING"

    local architecture codename
    architecture="$(dpkg --print-architecture)"
    # shellcheck disable=SC1091
    source /etc/os-release
    codename="$VERSION_CODENAME"
    printf '%s\n' \
      "deb [arch=$architecture signed-by=$MICROSOFT_KEYRING] https://packages.microsoft.com/repos/azure-cli/ $codename main" \
      >"$MICROSOFT_SOURCE"
    apt-get update
    apt-get install --yes azure-cli
  fi
}

configure_host_limits() {
  install -d -m 0755 "$STATE_DIR" "$CONFIG_DIR"
  touch "$MAINTENANCE_FILE"
  chmod 0644 "$MAINTENANCE_FILE"

  install -d -m 0755 /etc/systemd/journald.conf.d
  cat >/etc/systemd/journald.conf.d/lingosai.conf <<'EOF'
[Journal]
SystemMaxUse=100M
RuntimeMaxUse=50M
MaxRetentionSec=7day
Compress=yes
EOF

  if [[ ! -f /swapfile ]]; then
    fallocate -l 1G /swapfile
    chmod 0600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  if ! swapon --show=NAME --noheadings | sed 's/^[[:space:]]*//' | grep -Fxq /swapfile; then
    swapon /swapfile
  fi
  if ! grep -Eq '^/swapfile[[:space:]]+none[[:space:]]+swap[[:space:]]+sw[[:space:]]+0[[:space:]]+0$' /etc/fstab; then
    printf '%s\n' '/swapfile none swap sw 0 0' >>/etc/fstab
  fi

  systemctl enable docker.service
  systemctl restart docker.service
  systemctl restart systemd-journald.service
  dpkg-reconfigure --frontend=noninteractive unattended-upgrades
}

configure_caddy() {
  cat >/etc/caddy/Caddyfile <<EOF
{
	email support@lingosai.com
	admin off
}

$API_HOSTNAME {
	encode zstd gzip
	root * $STATE_DIR

	@maintenance file /maintenance
	handle @maintenance {
		header Cache-Control "no-store"
		header Retry-After "60"
		respond "LingosAI backend is temporarily unavailable." 503
	}

	handle {
		request_body {
			max_size 5MB
		}
		reverse_proxy 127.0.0.1:8000
	}
}
EOF

  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  systemctl enable caddy.service
  systemctl restart caddy.service
}

validate_environment_file() {
  local env_path="$1"
  [[ -s "$env_path" ]] || fail "Key Vault returned an empty environment"
  if grep -q $'\r' "$env_path"; then
    fail "the environment secret contains Windows line endings"
  fi

  local required
  for required in \
    ENVIRONMENT=production \
    DEBUG=false \
    DATABASE_AUTH_MODE=azure-managed-identity \
    AUTH_COOKIE_SECURE=true \
    AI_RATE_LIMIT_BACKEND=memory \
    WEB_CONCURRENCY=1 \
    STORAGE_BACKEND=azure; do
    grep -Fxq "$required" "$env_path" \
      || fail "the environment secret is missing required setting: $required"
  done

  # Angle-bracket email display names contain "@"; reviewed placeholders do
  # not. This rejects placeholders anywhere in a value without rejecting
  # EMAIL_FROM="LingosAI <noreply@lingosai.com>".
  if grep -Eq '<[^>@]+>' "$env_path"; then
    fail "the environment secret still contains a placeholder"
  fi
  if ! grep -Eq '^DATABASE_URL=postgresql://vm-lingosai-prod@[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\.postgres\.database\.azure\.com:5432/lingosai\?sslmode=require$' "$env_path"; then
    fail "the Azure database URL does not match the reviewed managed-identity contract"
  fi
  if grep -Eq '^DATABASE_URL=.*://[^/@:]+:[^/@]+@' "$env_path"; then
    fail "the Azure database URL must not contain a password"
  fi
}

fetch_environment_from_key_vault() {
  export AZURE_CORE_OUTPUT=none
  az login --identity --output none --only-show-errors

  env_tmp="$(mktemp)"
  az keyvault secret show \
    --vault-name "$KEY_VAULT_NAME" \
    --name "$ENV_SECRET_NAME" \
    --query value \
    --output tsv \
    --only-show-errors >"$env_tmp"

  validate_environment_file "$env_tmp"
  install -o root -g root -m 0600 "$env_tmp" "$ENV_FILE"
  [[ "$(stat -c '%U:%G' "$ENV_FILE")" == "root:root" ]] \
    || fail "$ENV_FILE ownership is unsafe"
  [[ "$(stat -c '%a' "$ENV_FILE")" == "600" ]] \
    || fail "$ENV_FILE permissions are unsafe"
}

main() {
  require_inputs
  trap cleanup EXIT
  install_base_packages
  install_caddy
  install_azure_cli
  configure_host_limits
  configure_caddy
  fetch_environment_from_key_vault
  log "Azure VM host contract installed; maintenance mode remains active."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
