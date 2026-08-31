#!/usr/bin/env bash

# Builds, validates, and uploads the LingosAI production environment file.
#
# The file this produces holds every production secret. It is written outside
# the repository, is never committed, and `upload` destroys it once Key Vault
# has it. Nothing here prints a secret value.
#
# The point of the script is that a bad environment file is caught on your
# laptop instead of by a crash-looping container on the VM. It runs the same
# two gates the file has to survive in production:
#
#   Gate A  validate_environment_file() sourced directly from
#           .github/scripts/azure-vm-bootstrap.sh — literally the function the
#           VM runs before installing /etc/lingosai/backend.env.
#   Gate B  the application's own _guard_production() in app/core/config.py,
#           exercised by really constructing Settings against the file.
#
# Usage:
#   scripts/build-prod-env.sh init      seed the working file from the template
#   scripts/build-prod-env.sh edit      open it in $EDITOR
#   scripts/build-prod-env.sh check     run Gate A and Gate B
#   scripts/build-prod-env.sh upload    check, then store it in Key Vault, then shred
#   scripts/build-prod-env.sh diff      show which keys are still placeholders

set -Eeuo pipefail
umask 077

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEMPLATE="$REPO_ROOT/.env.production.example"
readonly BOOTSTRAP="$REPO_ROOT/.github/scripts/azure-vm-bootstrap.sh"
readonly WORK_FILE="${LINGOSAI_PROD_ENV_FILE:-/tmp/lingosai-backend.env}"

# Deliberately NOT named KEY_VAULT_NAME / ENV_SECRET_NAME: run_gate_a sources
# azure-vm-bootstrap.sh, which declares those two as readonly from its own
# positional arguments, and a collision aborts the sourced script.
readonly VAULT_NAME="kv-lingosai-e231"
readonly SECRET_NAME="backend-env"

info() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- init --------

# Pre-fills every value this deployment already knows, so the only things left
# by hand are the actual secrets. Refuses to clobber an existing working file.
seed_working_file() {
  [[ -f "$TEMPLATE" ]] || die "missing template: $TEMPLATE"
  if [[ -e "$WORK_FILE" ]]; then
    die "$WORK_FILE already exists. Edit it, or remove it to start over."
  fi

  python3 - "$TEMPLATE" "$WORK_FILE" <<'PY'
import sys

template, target = sys.argv[1], sys.argv[2]

# Deployment-specific values that are not secret and are already known from the
# live subscription. Everything absent from here stays a <placeholder> for the
# operator to fill in by hand.
known = {
    "DATABASE_URL": (
        "postgresql://vm-lingosai-prod@"
        "psql-lingosai-e231.postgres.database.azure.com:5432/lingosai?sslmode=require"
    ),
    "CORS_ORIGINS": "https://www.lingosai.com,https://lingosai.com",
    "FRONTEND_URL": "https://www.lingosai.com",
    "GOOGLE_REDIRECT_URI": "https://api.lingosai.com/auth/google/callback",
    "AZURE_BLOB_PUBLIC_ACCOUNT_URL": "https://stlingosaipube231.blob.core.windows.net",
    "AZURE_BLOB_PRIVATE_ACCOUNT_URL": "https://stlingosaiprive231.blob.core.windows.net",
    "AZURE_SPEECH_REGION": "eastus",
}

out = []
for line in open(template, encoding="utf-8").read().splitlines():
    stripped = line.lstrip()
    if stripped and not stripped.startswith("#") and "=" in line:
        key = line.split("=", 1)[0]
        if key in known:
            line = f"{key}={known[key]}"
    out.append(line)

# Written with Unix line endings and a trailing newline: the host validator
# rejects CRLF outright.
open(target, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
PY

  chmod 0600 "$WORK_FILE"
  info "Seeded $WORK_FILE (mode 0600)."
  echo
  report_placeholders || true
  echo
  cat <<EOF
Fill the values above by hand. Copy these straight from the repo-root .env:

  OPENAI_API_KEY  DEEPGRAM_API_KEY  AZURE_SPEECH_KEY  PINECONE_API_KEY
  LANGCHAIN_API_KEY  RESEND_API_KEY  GOOGLE_CLIENT_ID  GOOGLE_CLIENT_SECRET
  RAZORPAY_KEY_ID  RAZORPAY_KEY_SECRET  RAZORPAY_WEBHOOK_SECRET

Generate FRESH production values for these two - do not reuse the dev ones:

  openssl rand -hex 32     # JWT_SECRET
  openssl rand -hex 32     # OTP_HASHING_SECRET

Then:  scripts/build-prod-env.sh edit
       scripts/build-prod-env.sh check
       scripts/build-prod-env.sh upload
EOF
}

# Lists keys whose value still looks like an unfilled <placeholder>, or is empty
# when the template did not intend it to be. Prints key names only.
report_placeholders() {
  require_work_file
  python3 - "$WORK_FILE" <<'PY'
import re, sys

# SENTRY_DSN and REDIS_URL are deliberately empty in this deployment.
INTENTIONALLY_EMPTY = {"SENTRY_DSN", "REDIS_URL"}

# The host validator's placeholder rule, applied to the WHOLE file exactly as
# azure-vm-bootstrap.sh applies it: an angle-bracket run with no "@" inside.
# That keeps EMAIL_FROM's <noreply@lingosai.com> legitimate, and it catches a
# placeholder left in a COMMENT, which would fail Gate A just as hard.
PLACEHOLDER = re.compile(r"<[^>@]+>")

pending = []
empty = []
stray = []
for number, line in enumerate(open(sys.argv[1], encoding="utf-8"), start=1):
    line = line.rstrip("\n")
    stripped = line.lstrip()
    is_setting = bool(stripped) and not stripped.startswith("#") and "=" in line
    if not is_setting:
        if PLACEHOLDER.search(line):
            stray.append((number, stripped[:70]))
        continue
    key, value = line.split("=", 1)
    if PLACEHOLDER.search(value):
        pending.append(key)
    elif not value and key not in INTENTIONALLY_EMPTY:
        empty.append(key)

if pending:
    print("Still placeholders (%d):" % len(pending))
    for key in pending:
        print("  " + key)
if stray:
    print("Placeholder text outside a setting (%d) - Gate A rejects these too:" % len(stray))
    for number, text in stray:
        print("  line %d: %s" % (number, text))
if empty:
    print("Empty (%d) - confirm each is meant to be blank:" % len(empty))
    for key in empty:
        print("  " + key)
if not pending and not stray and not empty:
    print("No placeholders left.")
sys.exit(1 if pending or stray else 0)
PY
}

require_work_file() {
  [[ -f "$WORK_FILE" ]] || die "$WORK_FILE does not exist. Run: $0 init"
}

# --------------------------------------------------------------- gate A -------

# Sources the real host script and calls its validator, so this check cannot
# drift from what the VM enforces. The bootstrap script guards its own main()
# behind a BASH_SOURCE test, so sourcing it defines functions and runs nothing.
run_gate_a() {
  [[ -f "$BOOTSTRAP" ]] || die "missing host bootstrap script: $BOOTSTRAP"
  info "Gate A - host contract (validate_environment_file from azure-vm-bootstrap.sh)"

  # Run in a subshell: the sourced script sets readonly globals and its own
  # shell options, and `fail` exits, which must not kill this script.
  if (
    # shellcheck source=/dev/null
    source "$BOOTSTRAP"
    validate_environment_file "$WORK_FILE"
  ); then
    echo "  PASS"
  else
    die "Gate A failed - the VM bootstrap would reject this file."
  fi
}

# --------------------------------------------------------------- gate B -------

# Really constructs Settings against the file, so _guard_production runs exactly
# as it will at container start. Only the pass/fail message is printed.
run_gate_b() {
  info "Gate B - application production guard (_guard_production in app/core/config.py)"
  command -v uv >/dev/null 2>&1 || die "uv is required to run the application guard"

  if (cd "$REPO_ROOT/backend" && LINGOSAI_ENV_FILE="$WORK_FILE" uv run --quiet python - <<'PY'
import os
import sys

from pydantic_settings import SettingsConfigDict

from app.core.config import Settings

Settings.model_config = SettingsConfigDict(
    env_file=os.environ["LINGOSAI_ENV_FILE"],
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)

try:
    Settings()
except Exception as exc:  # noqa: BLE001 - surface the guard's own message
    # Print only the guard's own violation lines. Pydantic's full error dump
    # echoes a repr of the parsed settings, which would put secret values on
    # the terminal and into any captured output.
    violations = [
        # Drop pydantic's trailing "[type=..., input_value=...]" annotation: it
        # carries a repr of the parsed settings.
        line.strip().split("[type=")[0].strip()
        for line in str(exc).splitlines()
        if line.strip().startswith("-")
    ]
    if violations:
        print("Unsafe production configuration:", file=sys.stderr)
        for violation in violations:
            print("  " + violation, file=sys.stderr)
    else:
        print(type(exc).__name__ + ": see app/core/config.py", file=sys.stderr)
        for line in str(exc).splitlines():
            if "[type=" not in line and "input_value" not in line:
                print("  " + line.strip(), file=sys.stderr)
    sys.exit(1)
print("production config OK")
PY
  ); then
    echo "  PASS"
  else
    die "Gate B failed - the application would refuse to boot with this file."
  fi
}

run_checks() {
  require_work_file

  local mode
  mode="$(stat -f '%Lp' "$WORK_FILE" 2>/dev/null || stat -c '%a' "$WORK_FILE")"
  if ((8#$mode > 8#600)); then
    warn "$WORK_FILE is mode $mode; tightening to 0600"
    chmod 0600 "$WORK_FILE"
  fi

  if ! report_placeholders; then
    die "fill the remaining placeholders before checking"
  fi
  echo
  run_gate_a
  run_gate_b
  echo
  info "Both gates passed. Ready to upload."
}

# --------------------------------------------------------------- upload -------

upload_to_key_vault() {
  run_checks
  echo

  command -v az >/dev/null 2>&1 || die "the Azure CLI is required"
  az account show --output none 2>/dev/null || die "not signed in: run 'az login'"

  info "Uploading to Key Vault $VAULT_NAME as secret '$SECRET_NAME'"
  echo "The previous version stays available as a rollback."
  read -r -p "Type 'upload' to continue: " confirm
  [[ "$confirm" == "upload" ]] || die "aborted"

  az keyvault secret set \
    --vault-name "$VAULT_NAME" \
    --name "$SECRET_NAME" \
    --file "$WORK_FILE" \
    --output none

  local version
  version="$(az keyvault secret show \
    --vault-name "$VAULT_NAME" \
    --name "$SECRET_NAME" \
    --query id \
    --output tsv)"
  info "Stored: $version"

  if command -v shred >/dev/null 2>&1; then
    shred -u "$WORK_FILE"
  else
    rm -P "$WORK_FILE" 2>/dev/null || rm -f "$WORK_FILE"
  fi
  info "Local copy destroyed."
  echo
  cat <<EOF
The VM does not pick this up on its own. Next, from MASTER_PLAN.md Phase 3:
re-run the host bootstrap so the VM re-reads the secret, then redeploy so the
container restarts with the new environment.
EOF
}

open_editor() {
  require_work_file
  "${EDITOR:-vi}" "$WORK_FILE"
}

main() {
  case "${1:-}" in
    init) seed_working_file ;;
    edit) open_editor ;;
    check) run_checks ;;
    upload) upload_to_key_vault ;;
    diff | status) report_placeholders || true ;;
    *)
      sed -n '3,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 1
      ;;
  esac
}

main "$@"
