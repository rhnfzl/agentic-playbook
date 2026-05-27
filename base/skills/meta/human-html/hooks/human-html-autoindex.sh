#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PostToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|Bash
# PLAYBOOK-HOOK-CURSOR-MATCHER: Edit|Write|MultiEdit|StrReplace|Shell
#
# PostToolUse autoindex hook. Canonical source lives with the human-html skill
# (skills/meta/human-html/hooks/) per the v0.6 hook-source unification. Root
# `hooks/human-html-autoindex.sh` symlinks here.
#
# Regenerates docs/human-html/index.html after direct editor writes, Codex
# apply_patch events, and shell commands that mention the human-html script
# or artifact directory.
#
# Contract:
#   * Always exit 0 (script's own check fails loudly on malformed artifacts;
#     we never block the upstream tool call).
#   * Resolves workspace root from $CLAUDE_PROJECT_DIR -> $CURSOR_PROJECT_DIR
#     -> $CODEX_WORKSPACE -> hook JSON .cwd -> pwd.
#   * Probes several known install locations for human_html_artifacts.py
#     (Codex USER skill root, Claude skill dir, Cursor skill dir, Windsurf
#     skill dir) so the hook works under any adapter's projection layout.

set -u

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

HOOK_CWD=$(jq -r '.cwd // empty' <<<"$INPUT")
WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${CURSOR_PROJECT_DIR:-${CODEX_WORKSPACE:-${HOOK_CWD:-$(pwd)}}}}"
ARTIFACT_DIR="$WORKSPACE_ROOT/docs/human-html"

SCRIPT_PATH=""
for candidate in \
  "$HOME/.agents/skills/human-html/human_html_artifacts.py" \
  "$HOME/.claude/skills/human-html/human_html_artifacts.py" \
  "$HOME/.cursor/skills/human-html/human_html_artifacts.py" \
  "$HOME/.codeium/windsurf/skills/human-html/human_html_artifacts.py"; do
  if [ -f "$candidate" ]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

[ -z "$SCRIPT_PATH" ] && exit 0

TOOL_NAME=$(jq -r '.tool_name // empty' <<<"$INPUT")
TARGET_PATH=$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<<"$INPUT")
COMMAND_TEXT=$(jq -r '.command // .tool_input.command // .tool_input.cmd // .tool_input.shell_command // empty' <<<"$INPUT")

case "$TOOL_NAME" in
  Write|Edit|MultiEdit|StrReplace|apply_patch|Bash|Shell|exec_command|functions.exec_command) : ;;
  *) exit 0 ;;
esac

if [ "$TOOL_NAME" = "apply_patch" ]; then
  [ -d "$ARTIFACT_DIR" ] || exit 0
  (cd "$WORKSPACE_ROOT" && python3 "$SCRIPT_PATH" index) >&2 2>&1 || true
  exit 0
fi

case "$TOOL_NAME" in
  Bash|Shell|exec_command|functions.exec_command)
    case "$COMMAND_TEXT" in
      *human_html_artifacts.py*|*docs/human-html*) : ;;
      *) exit 0 ;;
    esac
    [ -d "$ARTIFACT_DIR" ] || exit 0
    (cd "$WORKSPACE_ROOT" && python3 "$SCRIPT_PATH" index) >&2 2>&1 || true
    exit 0
    ;;
esac

[ -z "$TARGET_PATH" ] && exit 0

if [[ "$TARGET_PATH" != /* ]]; then
  TARGET_PATH="$WORKSPACE_ROOT/$TARGET_PATH"
fi

case "$TARGET_PATH" in
  "$ARTIFACT_DIR"/*) : ;;
  *) exit 0 ;;
esac

case "$TARGET_PATH" in
  *.html) : ;;
  *) exit 0 ;;
esac

case "$TARGET_PATH" in
  "$ARTIFACT_DIR/index.html") exit 0 ;;
esac

(cd "$WORKSPACE_ROOT" && python3 "$SCRIPT_PATH" index) >&2 2>&1 || true

exit 0
