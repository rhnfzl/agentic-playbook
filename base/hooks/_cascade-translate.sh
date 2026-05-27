#!/usr/bin/env bash
# Windsurf Cascade -> Claude-shaped stdin translator (v0.6).
#
# Cascade hook events deliver stdin in a different shape than Claude/Codex:
#
#   Claude:   {tool_name, tool_input: {file_path|command|...}, cwd}
#   Cascade:  {agent_action_name, trajectory_id, execution_id, timestamp,
#              model_name, tool_info: {command_line|file_path|user_prompt|
#                                       response|transcript_path|cwd}}
#
# Playbook hooks expect Claude-shaped stdin. Rather than fork every script
# into a Cascade variant, this single translator script re-encodes the
# stdin JSON and pipes it into the original hook. Wire-up:
#
#   ~/.codeium/windsurf/hooks.json:
#     "pre_run_command": [
#       {"command": "/abs/path/_cascade-translate.sh /abs/path/never-push-to-develop.sh"}
#     ]
#
# Underscore prefix in the filename keeps load_hooks() from registering
# this file as a regular hook (it has no PLAYBOOK-HOOK-EVENT header).
#
# Exit-code semantics: pre-hooks pass through the core hook's exit code so
# `exit 2` blocks the action (Cascade's blocking semantic). Post-hooks
# always exit 0 because Cascade ignores exit codes on post-hooks anyway.

set -u

CORE_HOOK="${1:-}"
if [ -z "$CORE_HOOK" ] || [ ! -x "$CORE_HOOK" ]; then
  # Misconfigured wrapper invocation: never block on it.
  exit 0
fi

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  # Without jq we can't translate; pass raw stdin and hope the core hook
  # tolerates the Cascade shape. Most playbook hooks gate on jq presence
  # and no-op when missing, so this is safe.
  echo "$INPUT" | "$CORE_HOOK"
  exit "$?"
fi

ACTION=$(jq -r '.agent_action_name // empty' <<<"$INPUT")
case "$ACTION" in
  pre_run_command|post_run_command) TOOL_NAME="Bash" ;;
  pre_write_code|post_write_code) TOOL_NAME="Write" ;;
  pre_read_code|post_read_code) TOOL_NAME="Read" ;;
  pre_mcp_tool_use|post_mcp_tool_use) TOOL_NAME="Mcp" ;;
  pre_user_prompt) TOOL_NAME="UserPrompt" ;;
  post_cascade_response*) TOOL_NAME="Stop" ;;
  post_setup_worktree) TOOL_NAME="SessionStart" ;;
  *) TOOL_NAME="${ACTION:-Other}" ;;
esac

# Translate Cascade shape to Claude shape. The core hook reads
# .tool_name, .tool_input.file_path / .command / .path / .notebook_path,
# .cwd, .command (Bash variants), so we populate the matching keys.
TRANSLATED=$(jq -c \
  --arg tool "$TOOL_NAME" \
  '. + {
     tool_name: $tool,
     tool_input: {
       file_path: (.tool_info.file_path // ""),
       path:      (.tool_info.file_path // ""),
       command:   (.tool_info.command_line // ""),
       user_prompt: (.tool_info.user_prompt // "")
     },
     command: (.tool_info.command_line // ""),
     cwd: (.tool_info.cwd // .cwd // "")
   }' <<<"$INPUT")

echo "$TRANSLATED" | "$CORE_HOOK"
core_exit=$?

# Pre-hooks: pass through exit code so `exit 2` blocks. Post-hooks: Cascade
# ignores exit code anyway; exit 0 keeps things clean.
case "$ACTION" in
  pre_*) exit "$core_exit" ;;
  *) exit 0 ;;
esac
