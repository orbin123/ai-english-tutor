#!/usr/bin/env bash

# Report what the LingosAI production environment is doing right now, and how
# much of the free 750-hour monthly VM allowance has been consumed.
#
#   scripts/azure-status.sh
#
# Read-only: it starts and stops nothing.
#
# The hours figure is derived from the Azure Activity Log's start/deallocate
# events on the VM, so it counts every wake regardless of what triggered it —
# these scripts, the GitHub workflows, or the portal. Activity Log retention is
# 90 days, which always covers the current calendar month.

# shellcheck source=scripts/_azure-common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/_azure-common.sh"

require_azure_cli

vm_state="$(vm_power_state)"
pg_state="$(postgres_state)"
window="$(active_until)"

bold "LingosAI production"
printf '  %-14s %s\n' "VM" "${vm_state#PowerState/}"
printf '  %-14s %s\n' "PostgreSQL" "$pg_state"

# --- live window -------------------------------------------------------------

if [[ -z "$window" || "$window" == "None" ]]; then
  printf '  %-14s %s\n' "Live window" "none set"
else
  remaining="$(python3 - "$window" <<'PY'
from datetime import datetime, timezone
import sys

try:
    deadline = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
except ValueError:
    print("malformed")
    raise SystemExit

seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
if seconds <= 0:
    print("expired")
else:
    hours, minutes = divmod(int(seconds) // 60, 60)
    print(f"{hours}h {minutes}m remaining")
PY
)"
  printf '  %-14s %s (%s)\n' "Live window" "$window" "$remaining"
fi

# --- public endpoint ---------------------------------------------------------

read -r code seconds <<<"$(probe_readiness)"
case "$code" in
  200) health="live (200 in ${seconds}s)" ;;
  503) health="warming or in maintenance (503)" ;;
  000) health="unreachable — expected while asleep" ;;
  *) health="unexpected HTTP $code" ;;
esac
printf '  %-14s %s\n' "Public API" "$health"

# --- free-tier hours ---------------------------------------------------------

echo
bold "VM hours this calendar month"

vm_id="$(az vm show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --query id \
  --output tsv \
  --only-show-errors)"

# Ask for slightly more than the month so far, then filter precisely in python.
offset_days="$(python3 -c "
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
print(min(89, (now - now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)).days + 1))
")"

# The Activity Log spells resource ids with a lowercase "resourcegroups", while
# `az vm show` returns "resourceGroups", so an equality filter here silently
# matches nothing. Fetch the ids and match case-insensitively in python.
# Written to a file rather than piped: the python below is itself supplied on
# stdin by its heredoc, so a pipe into it would be discarded.
events_file="$(mktemp)"
trap 'rm -f -- "$events_file"' EXIT

az monitor activity-log list \
  --offset "${offset_days}d" \
  --resource-group "$RESOURCE_GROUP" \
  --max-events 2000 \
  --query "[?status.value=='Succeeded'].{t:eventTimestamp,op:operationName.value,id:resourceId}" \
  --output json \
  --only-show-errors >"$events_file" 2>/dev/null || printf '[]' >"$events_file"

python3 - "$vm_state" "$FREE_VM_HOURS" "$VM_HOURS_WARN_AT" "$vm_id" "$events_file" <<'PY'
import json
import sys
from datetime import datetime, timezone

running_now = sys.argv[1] == "PowerState/running"
allowance = int(sys.argv[2])
warn_at = int(sys.argv[3])
vm_id = sys.argv[4].lower()
events_path = sys.argv[5]

now = datetime.now(timezone.utc)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

try:
    with open(events_path, encoding="utf-8") as handle:
        events = json.load(handle)
except (OSError, json.JSONDecodeError):
    events = []


def parse(stamp: str) -> datetime:
    # Activity Log timestamps carry sub-second precision of varying length.
    stamp = stamp.replace("Z", "+00:00")
    head, _, tail = stamp.partition(".")
    if tail:
        fraction, _, offset = tail.partition("+")
        stamp = f"{head}.{fraction[:6]}+{offset}"
    return datetime.fromisoformat(stamp)


power = []
for event in events:
    if (event.get("id") or "").lower() != vm_id:
        continue
    operation = event["op"]
    if operation.endswith("/start/action"):
        power.append((parse(event["t"]), "start"))
    elif operation.endswith("/deallocate/action"):
        power.append((parse(event["t"]), "stop"))
power.sort()

# Reconstruct running intervals, clipped to this calendar month. If the first
# event in the window is a stop, the VM was already running when the month
# began, so the interval opens at month start.
seconds = 0.0
opened = None
for moment, kind in power:
    if kind == "start":
        if opened is None:
            opened = moment
    else:
        start = opened if opened is not None else month_start
        opened = None
        start = max(start, month_start)
        if moment > start:
            seconds += (moment - start).total_seconds()

if opened is not None or running_now:
    start = max(opened or month_start, month_start)
    seconds += (now - start).total_seconds()

hours = seconds / 3600
percent = hours / allowance * 100
bar_width = 30
filled = min(bar_width, int(bar_width * hours / allowance))

print(f"  [{'#' * filled}{'.' * (bar_width - filled)}]  {hours:.1f} / {allowance} h ({percent:.0f}%)")

if not power:
    print("  NOTE: no VM power events in the Activity Log — treat this as a floor.")
if hours >= allowance:
    print("  OVER the free allowance: further VM hours this month are billed.")
elif hours >= warn_at:
    print(f"  Approaching the allowance ({allowance - hours:.0f} h left). Keep windows short.")
PY

echo
if [[ "$vm_state" == "PowerState/running" ]]; then
  note "Running now. Sleep it with:  scripts/azure-down.sh"
else
  note "Cold. Wake it with:  scripts/azure-up.sh 4"
fi
