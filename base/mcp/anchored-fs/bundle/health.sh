#!/usr/bin/env bash
# anchored-fs health check (per ADR-0026 bundle lifecycle convention, v0.5 extension).
#
# Read-only verification that anchored-fs is installed and wired up. Reports
# manifest presence, hook registration in ~/.claude/settings.json, venv state,
# launchd plist (macOS), and the agent-shared run/state directories. Delegates
# to install.py check; no mutation.
#
# Exit code 0 iff every probe passes. Non-zero indicates the bundle needs
# bootstrap.sh re-run (or hand-investigation if state is unexpected).

set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${bundle_dir}/install.py" check "$@"
