#!/usr/bin/env bash
# Cron / launchd wrapper for scripts/sync_distribution.py (ADR-0042).
#
# Install this wrapper at a path outside the playbook checkout (e.g.
# ~/.local/bin/playbook-distribution-sync.sh) and point cron at it.
# Edit the PLAYBOOK_HOME + DISTRIBUTION_MANIFEST lines before installing.
#
# Cron entry (example, runs daily at 09:00 local time):
#   0 9 * * * /Users/<you>/.local/bin/playbook-distribution-sync.sh
#
# macOS launchd alternative (catches up if the laptop was asleep at 09:00):
# Create ~/Library/LaunchAgents/com.<you>.playbook-distribution-sync.plist
# with StartCalendarInterval Hour=9 Minute=0 + RunAtLoad=false.

# `pipefail` makes the pipeline exit code reflect the python step (the
# `tee` always succeeds). `set -e` is intentionally off inside the
# branch so we can capture the exit code before the trap.
set -uo pipefail

# Edit these two paths before installing.
PLAYBOOK_HOME="${PLAYBOOK_HOME:-/Users/<you>/path/to/playbook}"
DISTRIBUTION_MANIFEST="${DISTRIBUTION_MANIFEST:-/Users/<you>/path/to/distribution-manifest.toml}"

LOG_PATH="${HOME}/Library/Logs/playbook-distribution-sync.log"
LOG_DIR="$(dirname "$LOG_PATH")"
mkdir -p "$LOG_DIR"

cd "$PLAYBOOK_HOME"

# Stamp the log so each invocation is visible at the tail.
{
  echo ""
  echo "--- $(date -u +%Y-%m-%dT%H:%M:%SZ) cron fire ---"
} >> "$LOG_PATH"

# Capture stdout + stderr; tee to log file. PIPESTATUS captures the
# python step's exit code BEFORE `tee` (whose status is always 0).
# Critical: don't use `if ! cmd | tee; then rc=$?`, because the `!` in
# the predicate inverts the status, so $? inside the branch is 0 even
# when the command failed, and the wrapper would exit 0 on failure.
python3 scripts/sync_distribution.py --manifest "$DISTRIBUTION_MANIFEST" 2>&1 | tee -a "$LOG_PATH"
rc=${PIPESTATUS[0]}

if [ "$rc" -ne 0 ]; then
  /usr/bin/osascript -e "display notification \"Sync failed (exit $rc); tail $LOG_PATH for details\" with title \"Playbook distribution\"" >/dev/null 2>&1 || true
  exit "$rc"
fi

# Optional: also sync curated memory entries on the same cadence. Memory
# failures are surfaced but do not raise a notification (lower stakes
# than content drift; the operator catches up next sync).
python3 scripts/sync_distribution.py memory --manifest "$DISTRIBUTION_MANIFEST" 2>&1 | tee -a "$LOG_PATH"
mem_rc=${PIPESTATUS[0]}
if [ "$mem_rc" -ne 0 ]; then
  /usr/bin/osascript -e "display notification \"Memory sync exit $mem_rc (non-blocking); tail $LOG_PATH\" with title \"Playbook distribution\"" >/dev/null 2>&1 || true
fi
exit "$rc"
