#!/usr/bin/env bash

# Wake the LingosAI production environment for a bounded number of hours.
#
#   scripts/azure-up.sh          # 6 hours (the default)
#   scripts/azure-up.sh 2        # 2 hours
#
# The window is a tag on the resource group. The hourly sleep watchdog reads it
# and forces the environment cold once it expires, so forgetting to run
# azure-down.sh costs you the rest of the window, not the rest of the month.
#
# Order matters and is owned by azure-control-plane.sh: PostgreSQL first
# (the app cannot start without it), then the VM, then the in-guest wake that
# restarts the container and only lifts Caddy's maintenance page once the
# application answers locally.

# shellcheck source=scripts/_azure-common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/_azure-common.sh"

readonly DEFAULT_HOURS=6
readonly HOURS="${1:-$DEFAULT_HOURS}"

# Checked here as well as in the control plane so a typo fails before anything
# starts costing money.
if [[ ! "$HOURS" =~ ^([1-9]|1[0-9]|2[0-4])$ ]]; then
  die "hours must be a whole number from 1 to 24 (got: $HOURS)"
fi

require_azure_cli

bold "Waking LingosAI production for $HOURS hour(s)"
note "resource group: $RESOURCE_GROUP"
note "VM:             $VM_NAME"
note "PostgreSQL:     $POSTGRES_SERVER"
echo

run_control_plane wake "$HOURS"

# The control plane stops once the VM reports healthy from inside the guest.
# Everything below is about the path the public actually takes: DNS, then
# Caddy, then TLS, then the app. Any of those can be the broken link.
echo
bold "Waiting for $API_ORIGIN to answer publicly"

readonly MAX_ATTEMPTS=40
for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  read -r code seconds <<<"$(probe_readiness)"

  case "$code" in
    200)
      echo
      bold "Ready."
      note "$API_ORIGIN/health/ready answered 200 in ${seconds}s"
      note "Active until: $(active_until)"
      echo
      note "Put it back to sleep when you are done:  scripts/azure-down.sh"
      exit 0
      ;;
    503)
      printf '  attempt %2d/%d: 503 - still warming (maintenance page)\n' \
        "$attempt" "$MAX_ATTEMPTS"
      ;;
    000)
      printf '  attempt %2d/%d: no response yet\n' "$attempt" "$MAX_ATTEMPTS"
      ;;
    *)
      printf '  attempt %2d/%d: HTTP %s\n' "$attempt" "$MAX_ATTEMPTS" "$code"
      ;;
  esac
  sleep 10
done

echo
warn "Compute is up, but $API_ORIGIN never returned 200."
cat >&2 <<EOF

  The infrastructure woke; something between the public URL and the app did
  not. Worth checking, in order:

    scripts/azure-status.sh          what is actually up
    az vm run-command invoke -g $RESOURCE_GROUP -n $VM_NAME \\
      --command-id RunShellScript \\
      --scripts 'docker logs --tail 50 lingosai-backend'

  A persistent 503 with the VM running usually means the container is not
  healthy, so the maintenance marker at /var/lib/lingosai/maintenance was
  never removed. That is normal before the first deployment.
EOF
exit 1
