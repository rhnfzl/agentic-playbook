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

set -euo pipefail

# Edit these two paths before installing.
PLAYBOOK_HOME="${PLAYBOOK_HOME:-/Users/<you>/path/to/playbook}"
DISTRIBUTION_MANIFEST="${DISTRIBUTION_MANIFEST:-/Users/<you>/path/to/distribution-manifest.toml}"

LOG_PATH="${HOME}/Library/Logs/playbook-distribution-sync.log"
LOG_DIR="$(dirname "$LOG_PATH")"
mkdir -p "$LOG_DIR"

cd "$PLAYBOOK_HOME"

# Capture stdout + stderr; tee to log file. Use exit code from python.
if ! python3 scripts/sync_distribution.py --manifest "$DISTRIBUTION_MANIFEST" 2>&1 | tee -a "$LOG_PATH"; then
  rc=$?
  # macOS native notification on failure.
  /usr/bin/osascript -e "display notification \"Sync failed; tail $LOG_PATH for details\" with title \"Playbook distribution\"" || true
  exit "$rc"
fi
