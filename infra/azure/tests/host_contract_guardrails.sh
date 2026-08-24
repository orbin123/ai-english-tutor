#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
bootstrap="$repo_root/.github/scripts/azure-vm-bootstrap.sh"
verify="$repo_root/.github/scripts/azure-vm-verify.sh"
deploy="$repo_root/.github/scripts/azure-vm-deploy.sh"
postgres_bootstrap="$repo_root/.github/scripts/azure-postgres-identity-bootstrap.sh"
postgres_python="$repo_root/backend/scripts/bootstrap_azure_postgres.py"

for script in "$bootstrap" "$verify" "$deploy" "$postgres_bootstrap"; do
  [[ -x "$script" ]] || {
    printf '%s must be executable.\n' "$script" >&2
    exit 1
  }
  bash -n "$script"
done

for script in "$bootstrap" "$verify"; do
  grep -Eq 'EXPECTED_API_HOSTNAME="api\.lingosai\.com"' "$script"
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

HOST_SCRIPT="$postgres_bootstrap" bash -c '
  set -- \
    lingosai-test-postgres \
    lingosai-postgres-administrators \
    11111111-2222-3333-4444-555555555555 \
    8.8.8.8
  source "$HOST_SCRIPT"
  require_inputs
'
if HOST_SCRIPT="$postgres_bootstrap" bash -c '
  set -- \
    lingosai-test-postgres \
    lingosai-postgres-administrators \
    11111111-2222-3333-4444-555555555555 \
    10.0.0.10
  source "$HOST_SCRIPT"
  require_inputs
' >/dev/null 2>&1; then
  printf 'PostgreSQL bootstrap accepted a private operator address.\n' >&2
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

grep -Eq 'az login --identity' "$bootstrap"
grep -Eq 'az keyvault secret show' "$bootstrap"
grep -Eq -- '--query value' "$bootstrap"
grep -Eq 'install -o root -g root -m 0600' "$bootstrap"
grep -Eq 'DATABASE_AUTH_MODE=azure-managed-identity' "$bootstrap"
grep -Eq 'DATABASE_URL=postgresql://vm-lingosai-prod@' "$bootstrap"
grep -Eq 'STORAGE_BACKEND=azure' "$bootstrap"
grep -Eq 'request_body' "$bootstrap"
grep -Eq 'max_size 5MB' "$bootstrap"
grep -Eq 'dpkg --compare-versions.*caddy_version' "$bootstrap"
caddy_source_removal="rm -f -- \"\$CADDY_SOURCE\""
grep -Fq "$caddy_source_removal" "$bootstrap"
[[ "$(grep -nF "$caddy_source_removal" "$bootstrap" | head -n1 | cut -d: -f1)" -lt \
  "$(grep -nF 'apt-get update' "$bootstrap" | head -n1 | cut -d: -f1)" ]]
[[ "$(grep -cF 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' "$bootstrap")" == "1" ]]
grep -Eq 'reverse_proxy 127\.0\.0\.1:8000' "$bootstrap"
grep -Eq '@maintenance file /maintenance' "$bootstrap"
grep -Eq 'SystemMaxUse=100M' "$bootstrap"
grep -Eq 'fallocate -l 1G /swapfile' "$bootstrap"

grep -Eq 'az keyvault secret show' "$verify"
grep -Eq -- '--query id' "$verify"
grep -Eq 'az acr login' "$verify"
grep -Eq -- '--expose-token' "$verify"
grep -Eq '/dev/tcp/.*/5432' "$verify"

grep -Eq 'FIREWALL_RULE="temporary-identity-bootstrap"' "$postgres_bootstrap"
grep -Eq 'trap delete_temporary_firewall_rule EXIT' "$postgres_bootstrap"
grep -Eq 'firewall-rule delete' "$postgres_bootstrap"
grep -Eq -- '--start-ip-address "\$OPERATOR_IPV4"' "$postgres_bootstrap"
grep -Eq -- '--end-ip-address "\$OPERATOR_IPV4"' "$postgres_bootstrap"
grep -Eq 'AzureCliCredential' "$postgres_python"
grep -Eq 'pgaadauth_create_principal_with_oid' "$postgres_python"
grep -Eq "'service', false, false" "$postgres_python"
grep -Eq 'CREATE DATABASE' "$postgres_python"
grep -Eq 'APPLICATION_ROLE = "vm-lingosai-prod"' "$postgres_python"

forbidden='client[_-]?secret|administrator_password|docker[[:space:]]+run.*--privileged|0\.0\.0\.0/0'
if grep -Eiq "$forbidden" \
  "$bootstrap" \
  "$verify" \
  "$postgres_bootstrap" \
  "$postgres_python"; then
  printf 'Forbidden host bootstrap pattern detected.\n' >&2
  exit 1
fi

printf 'Azure VM host-contract guardrails passed.\n'
