#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|NotebookEdit|StrReplace
# PLAYBOOK-HOOK-ADAPTERS: cursor
# PLAYBOOK-HOOK-CURSOR-ONLY: true
# (CURSOR-ONLY retained as a deprecation breadcrumb -- the ADAPTERS
#  header is the canonical mechanism per ADR-0037; ADR amendment in
#  v0.8 keeps both during the transition window so adapters that read
#  the old header still work. Future removal: drop CURSOR-ONLY once
#  every callsite reads ADAPTERS.)
#
# Cursor preToolUse wrapper for human-html-advisory.sh.
#
# Cursor surfaces hook guidance via JSON stdout (snake_case agent_message),
# not stderr. The core advisory hook stays agent-neutral and prints to stderr
# for Claude Code / Codex / Cline / Copilot.
#
# Output contract (per Cursor docs + Tavily 2026):
#   * If core hook had stderr content (heuristic matched): emit
#       {"permission":"allow","agent_message":"<stderr>"}
#     on stdout, exit 0. permission:"allow" is REQUIRED on Cursor stdout JSON;
#     omitting it would make the response invalid.
#   * If core hook had no stderr: exit 0 silently.
#
# CORE_HOOK is resolved relative to this script's installed path so the
# wrapper works under any adapter's hook directory (~/.cursor/hooks/, project
# .cursor/hooks/, etc.), not just the ~/.agents/skills/human-html/hooks/
# canonical location.

set -u

INPUT="$(cat)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORE_HOOK="$SCRIPT_DIR/human-html-advisory.sh"

stderr_file="$(mktemp "${TMPDIR:-/tmp}/human-html-advisory.XXXXXX")"
cleanup() {
  rm -f "$stderr_file"
}
trap cleanup EXIT

if [ ! -x "$CORE_HOOK" ]; then
  exit 0
fi

HOOK_CWD=""
if command -v jq >/dev/null 2>&1; then
  HOOK_CWD=$(jq -r '.cwd // empty' <<<"$INPUT")
fi

echo "$INPUT" | env CURSOR_PROJECT_DIR="${CURSOR_PROJECT_DIR:-$HOOK_CWD}" \
  "$CORE_HOOK" 2>"$stderr_file" || true

if [ ! -s "$stderr_file" ]; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  cat "$stderr_file" >&2
  exit 0
fi

jq -n --rawfile msg "$stderr_file" '{permission: "allow", agent_message: $msg}'
exit 0
