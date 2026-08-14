#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
bootstrap="$repo_root/.github/scripts/azure-vm-bootstrap.sh"
verify="$repo_root/.github/scripts/azure-vm-verify.sh"
deploy="$repo_root/.github/scripts/azure-vm-deploy.sh"

for script in "$bootstrap" "$verify" "$deploy"; do
  [[ -x "$script" ]] || {
    printf '%s must be executable.\n' "$script" >&2
    exit 1
  }
  bash -n "$script"
done

for script in "$bootstrap" "$verify"; do
  rg --quiet 'EXPECTED_API_HOSTNAME="api\.lingosai\.com"' "$script"
done

HOST_SCRIPT="$bootstrap" bash -c '
  id() { printf "0\n"; }
  set -- api.lingosai.com lingosai-test-vault backend-env
  source "$HOST_SCRIPT"
  require_inputs
'
if HOST_SCRIPT="$bootstrap" bash -c '
  id() { printf "0\n"; }
  set -- attacker.example.com lingosai-test-vault backend-env
  source "$HOST_SCRIPT"
  require_inputs
' >/dev/null 2>&1; then
  printf 'Bootstrap accepted an unreviewed API hostname.\n' >&2
  exit 1
fi

HOST_SCRIPT="$verify" bash -c '
  id() { printf "0\n"; }
  set -- \
    api.lingosai.com \
    lingosai-test-vault \
    backend-env \
    lingosaitestregistry \
    lingosai-test-postgres
  source "$HOST_SCRIPT"
  require_inputs
'
if HOST_SCRIPT="$verify" bash -c '
  id() { printf "0\n"; }
  set -- \
    api.lingosai.com \
    lingosai-test-vault \
    backend-env \
    Bad-Registry \
    lingosai-test-postgres
  source "$HOST_SCRIPT"
  require_inputs
' >/dev/null 2>&1; then
  printf 'Verifier accepted an invalid ACR name.\n' >&2
  exit 1
fi

HOST_SCRIPT="$bootstrap" bash -c '
  fixture="$(mktemp)"
  trap '\''unlink "$fixture"'\'' EXIT
  cat >"$fixture" <<EOF
ENVIRONMENT=production
DEBUG=false
DATABASE_AUTH_MODE=azure-managed-identity
DATABASE_URL=postgresql://vm-lingosai-prod@db1.postgres.database.azure.com:5432/lingosai?sslmode=require
AUTH_COOKIE_SECURE=true
AI_RATE_LIMIT_BACKEND=memory
WEB_CONCURRENCY=1
STORAGE_BACKEND=azure
EMAIL_FROM="LingosAI <noreply@lingosai.com>"
EOF
  set -- api.lingosai.com lingosai-test-vault backend-env
  source "$HOST_SCRIPT"
  validate_environment_file "$fixture"
'
if HOST_SCRIPT="$bootstrap" bash -c '
  fixture="$(mktemp)"
  trap '\''unlink "$fixture"'\'' EXIT
  cat >"$fixture" <<EOF
ENVIRONMENT=production
DEBUG=false
DATABASE_AUTH_MODE=azure-managed-identity
DATABASE_URL=postgresql://vm-lingosai-prod@<server>.postgres.database.azure.com:5432/lingosai?sslmode=require
AUTH_COOKIE_SECURE=true
AI_RATE_LIMIT_BACKEND=memory
WEB_CONCURRENCY=1
STORAGE_BACKEND=azure
EOF
  set -- api.lingosai.com lingosai-test-vault backend-env
  source "$HOST_SCRIPT"
  validate_environment_file "$fixture"
' >/dev/null 2>&1; then
  printf 'Bootstrap accepted an environment placeholder.\n' >&2
  exit 1
fi

rg --quiet 'az login --identity' "$bootstrap"
rg --quiet 'az keyvault secret show' "$bootstrap"
rg --quiet -- '--query value' "$bootstrap"
rg --quiet 'install -o root -g root -m 0600' "$bootstrap"
rg --quiet 'DATABASE_AUTH_MODE=azure-managed-identity' "$bootstrap"
rg --quiet 'DATABASE_URL=postgresql://vm-lingosai-prod@' "$bootstrap"
rg --quiet 'STORAGE_BACKEND=azure' "$bootstrap"
rg --quiet 'request_body' "$bootstrap"
rg --quiet 'max_size 5MB' "$bootstrap"
rg --quiet 'dpkg --compare-versions.*caddy_version' "$bootstrap"
rg --quiet 'reverse_proxy 127\.0\.0\.1:8000' "$bootstrap"
rg --quiet '@maintenance file /maintenance' "$bootstrap"
rg --quiet 'SystemMaxUse=100M' "$bootstrap"
rg --quiet 'fallocate -l 1G /swapfile' "$bootstrap"

rg --quiet 'az keyvault secret show' "$verify"
rg --quiet -- '--query id' "$verify"
rg --quiet 'az acr login' "$verify"
rg --quiet -- '--expose-token' "$verify"
rg --quiet '/dev/tcp/.*/5432' "$verify"

forbidden='client[_-]?secret|administrator_password|docker[[:space:]]+run.*--privileged|0\.0\.0\.0/0'
if rg --ignore-case "$forbidden" "$bootstrap" "$verify"; then
  printf 'Forbidden host bootstrap pattern detected.\n' >&2
  exit 1
fi

printf 'Azure VM host-contract guardrails passed.\n'
