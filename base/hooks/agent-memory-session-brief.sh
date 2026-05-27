#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: SessionStart
# PLAYBOOK-HOOK-MATCHER: *
# SessionStart hook: render a session opener from accumulated memory.
#
# When Claude Code or Codex starts a session, this hook calls
# agent_memory_bridge.py context to print a brief summary of recent memories
# relevant to the workspace. The output is captured by the agent runtime and
# included in the session opening context.
#
# Workspace resolution:
#   $CLAUDE_PROJECT_DIR -> $CODEX_WORKSPACE -> pwd
#
# Bridge location:
#   1. $AGENT_MEMORY_BRIDGE (explicit override)
#   2. ~/.config/agent-shared/mcp_servers/agent-memory-bridge/agent_memory_bridge.py
#   3. Workspace's own scripts/agent_memory_bridge.py
#
# Contract:
#   * Always exit 0; never block session start.
#   * Output goes to stdout for the agent runtime to capture.
#   * Quiet by default; set AGENT_MEMORY_BRIEF_VERBOSE=1 for debug logging.

set -u

WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_WORKSPACE:-$(pwd)}}"

resolve_bridge() {
  if [ -n "${AGENT_MEMORY_BRIDGE:-}" ] && [ -f "$AGENT_MEMORY_BRIDGE" ]; then
    printf '%s\n' "$AGENT_MEMORY_BRIDGE"
    return
  fi
  local shared="$HOME/.config/agent-shared/mcp_servers/agent-memory-bridge/agent_memory_bridge.py"
  if [ -f "$shared" ]; then
    printf '%s\n' "$shared"
    return
  fi
  local workspace_local="$WORKSPACE_ROOT/scripts/agent_memory_bridge.py"
  if [ -f "$workspace_local" ]; then
    printf '%s\n' "$workspace_local"
    return
  fi
  printf '\n'
}

BRIDGE="$(resolve_bridge)"

if [ -z "$BRIDGE" ]; then
  [ "${AGENT_MEMORY_BRIEF_VERBOSE:-0}" = "1" ] && echo "agent-memory-session-brief: bridge not found" >&2
  exit 0
fi

LIMIT="${AGENT_MEMORY_BRIEF_LIMIT:-5}"

# Render the brief. If context command fails, do not block session start.
(cd "$WORKSPACE_ROOT" && python3 "$BRIDGE" context --limit "$LIMIT") 2>/dev/null || {
  [ "${AGENT_MEMORY_BRIEF_VERBOSE:-0}" = "1" ] && echo "agent-memory-session-brief: context render failed" >&2
}

exit 0
