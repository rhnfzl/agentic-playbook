#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PostToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit
# PostToolUse hook: enforce a hard line cap on auto-memory MEMORY.md.
#
# When a tool writes to the workspace's MEMORY.md, invoke the memory_curator
# MCP script to demote lowest-priority entries to MEMORY_ARCHIVE.md so the
# index stays under the cap. Underlying memory files are untouched.
#
# Workspace resolution:
#   $CLAUDE_PROJECT_DIR -> $CODEX_WORKSPACE -> pwd
#
# MEMORY.md path resolution:
#   1. $MEMORY_INDEX_PATH (explicit override)
#   2. Encode WORKSPACE_ROOT into the Claude project slug
#      (s|/|-| → ~/.claude/projects/<slug>/memory/MEMORY.md)
#   3. Fallback: $HOME/.claude/projects/<encoded>/memory/MEMORY.md
#
# Curator location:
#   1. $MEMORY_CURATOR (explicit override)
#   2. ~/.config/agent-shared/mcp_servers/agent-memory-bridge/memory_curator.py
#      (the curator co-locates with agent_memory_bridge.py + agent_memory_mcp.py
#      inside the agent-memory-bridge MCP bundle; the playbook installer
#      symlinks the .py files from mcp/agent-memory-bridge/ to that target)
#   3. Workspace's own scripts/memory_curator.py
#
# Contract:
#   * Always exit 0; never block the upstream tool call.
#   * Only acts when the modified path equals the resolved MEMORY.md.

set -u

WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_WORKSPACE:-$(pwd)}}"

resolve_memory_path() {
  if [ -n "${MEMORY_INDEX_PATH:-}" ]; then
    printf '%s\n' "$MEMORY_INDEX_PATH"
    return
  fi
  local encoded
  encoded="$(printf '%s' "$WORKSPACE_ROOT" | sed 's|/|-|g')"
  printf '%s\n' "$HOME/.claude/projects/${encoded}/memory/MEMORY.md"
}

resolve_curator() {
  if [ -n "${MEMORY_CURATOR:-}" ] && [ -f "$MEMORY_CURATOR" ]; then
    printf '%s\n' "$MEMORY_CURATOR"
    return
  fi
  local shared="$HOME/.config/agent-shared/mcp_servers/agent-memory-bridge/memory_curator.py"
  if [ -f "$shared" ]; then
    printf '%s\n' "$shared"
    return
  fi
  local workspace_local="$WORKSPACE_ROOT/scripts/memory_curator.py"
  if [ -f "$workspace_local" ]; then
    printf '%s\n' "$workspace_local"
    return
  fi
  printf '\n'
}

MEMORY_PATH="$(resolve_memory_path)"
CURATOR="$(resolve_curator)"
CAP="${MEMORY_CURATOR_CAP:-200}"

[ -n "$CURATOR" ] || exit 0

INPUT="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

TOOL_NAME=$(jq -r '.tool_name // empty' <<<"$INPUT")
TARGET_PATH=$(jq -r '.tool_input.file_path // empty' <<<"$INPUT")

case "$TOOL_NAME" in
  Write|Edit|MultiEdit) : ;;
  *) exit 0 ;;
esac

[ -n "$TARGET_PATH" ] || exit 0
RESOLVED_TARGET=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$TARGET_PATH" 2>/dev/null)
RESOLVED_MEMORY=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$MEMORY_PATH" 2>/dev/null)

if [ "$RESOLVED_TARGET" != "$RESOLVED_MEMORY" ]; then
  exit 0
fi

MEMORY_INDEX_DIR="$(dirname "$MEMORY_PATH")" python3 "$CURATOR" --cap "$CAP" apply --quiet >/dev/null 2>&1 || true
exit 0
