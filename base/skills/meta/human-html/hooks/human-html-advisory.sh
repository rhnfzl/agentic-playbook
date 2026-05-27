#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|NotebookEdit
# PLAYBOOK-HOOK-CURSOR-MATCHER: Edit|Write|MultiEdit|NotebookEdit|StrReplace
# PLAYBOOK-HOOK-CURSOR-WRAPPER: human-html-advisory-cursor.sh
#
# PreToolUse advisory hook. Canonical source lives with the human-html skill
# (skills/meta/human-html/hooks/) per the v0.6 hook-source unification.
# Root `hooks/human-html-advisory.sh` symlinks here so the installer picks up
# one body and one set of headers.
#
# Nudges toward HTML when an HIL-shaped Markdown write is about to land
# outside the agreed Markdown lanes.
#
# Contract:
#   * Always exit 0 (advisory only, never block).
#   * Print suggestion to stderr; Claude Code and Codex surface hook output
#     back to the model. Cursor uses the sibling wrapper (snake_case JSON
#     agent_message) per PLAYBOOK-HOOK-CURSOR-WRAPPER convention.
#   * Heuristic uses filename slug, not file contents, so the hook is cheap.
#
# Workspace root resolution (first non-empty wins):
#   1. $CLAUDE_PROJECT_DIR (Claude Code)
#   2. $CURSOR_PROJECT_DIR (Cursor)
#   3. $CODEX_WORKSPACE (Codex)
#   4. hook JSON .cwd
#   5. pwd
#
# Workspace customization:
#   A file named .human-html-allowlist at the workspace root (one
#   glob-style path pattern per line, # for comments) appends entries to
#   the baseline allowlist.

set -u

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

HOOK_CWD=$(jq -r '.cwd // empty' <<<"$INPUT")
WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${CURSOR_PROJECT_DIR:-${CODEX_WORKSPACE:-${HOOK_CWD:-$(pwd)}}}}"

TOOL_NAME=$(jq -r '.tool_name // empty' <<<"$INPUT")
TARGET_PATH=$(jq -r '.tool_input.file_path // .tool_input.path // .tool_input.notebook_path // empty' <<<"$INPUT")

case "$TOOL_NAME" in
  Edit|Write|MultiEdit|NotebookEdit|StrReplace) : ;;
  *) exit 0 ;;
esac

[ -z "$TARGET_PATH" ] && exit 0

if [[ "$TARGET_PATH" != /* ]]; then
  TARGET_PATH="$WORKSPACE_ROOT/$TARGET_PATH"
fi

case "$TARGET_PATH" in
  *.md) : ;;
  *) exit 0 ;;
esac

REL="${TARGET_PATH#"$WORKSPACE_ROOT/"}"
BASENAME="$(basename "$TARGET_PATH")"
SLUG_LOWER="$(echo "$BASENAME" | tr '[:upper:]' '[:lower:]')"

allowlist_match=0

case "$BASENAME" in
  AGENTS.md|CLAUDE.md|README.md|CHANGELOG.md|DOCS_CONVENTIONS.md|DOCS_INDEX.md|MEMORY.md)
    allowlist_match=1 ;;
esac

case "$REL" in
  */.git/*|.git/*)            allowlist_match=1 ;;
  */.venv/*|.venv/*)          allowlist_match=1 ;;
  */.pytest_cache/*|.pytest_cache/*) allowlist_match=1 ;;
  */node_modules/*|node_modules/*)   allowlist_match=1 ;;
  */.agent-harness/*|.agent-harness/*) allowlist_match=1 ;;
  */.clawpatch/*|.clawpatch/*) allowlist_match=1 ;;
  */.codex/*|.codex/*)        allowlist_match=1 ;;
  */.claude/*|.claude/*)      allowlist_match=1 ;;
  */.cursor/*|.cursor/*)      allowlist_match=1 ;;
  */.worktrees/*|.worktrees/*) allowlist_match=1 ;;
  */reviews/*|reviews/*)      allowlist_match=1 ;;
  */tests/results/*|tests/results/*) allowlist_match=1 ;;
esac

case "$REL" in
  docs/superpowers/*|docs/drafts/*|docs/tickets/*|docs/references/*|docs/contracts/*) allowlist_match=1 ;;
  docs/architecture/*|docs/adr/*|docs/agents/*|docs/reports/*|docs/presentations/*) allowlist_match=1 ;;
  meetings/*|archive/*|platform/*|external/*|graphify-out/*) allowlist_match=1 ;;
esac

ALLOWLIST_FILE="$WORKSPACE_ROOT/.human-html-allowlist"
if [ "$allowlist_match" = "0" ] && [ -f "$ALLOWLIST_FILE" ]; then
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    case "$pattern" in
      ""|"#"*) continue ;;
    esac
    pattern="$(echo "$pattern" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [ -z "$pattern" ] && continue
    # shellcheck disable=SC2254
    case "$REL" in
      $pattern) allowlist_match=1; break ;;
    esac
  done < "$ALLOWLIST_FILE"
fi

[ "$allowlist_match" = "1" ] && exit 0

case "$SLUG_LOWER" in
  *plan*|*review*|*audit*|*architecture*|*-arch-*|*-arch.md|*explainer*|*understanding*) match=1 ;;
  *research*|*decision*|*prototype*|*status*|*report*|*incident*|*postmortem*|*post-mortem*) match=1 ;;
  *) match=0 ;;
esac

if [ "$match" != "1" ]; then
  exit 0
fi

cat >&2 <<EOF
human-html advisory: \`$REL\` looks like a human-in-loop artifact written in Markdown.

The agreed contract (see the human-html skill SKILL.md):
  * Markdown is fine for agent scratch, references, ticket notes, meetings, drafts.
  * Human review surfaces (plan / review / architecture / understanding /
    research / decision / prototype / status / incident) belong in
    docs/human-html/ as HTML.

If this file is for human review, scaffold via the human-html skill's
human_html_artifacts.py new <kind> "<title>" command.

If this file is agent scratch or a durable reference, ignore this advisory.
Hook exits 0; the write will proceed regardless.

To add this file's directory to the workspace allowlist, append a glob to
$WORKSPACE_ROOT/.human-html-allowlist.
EOF

exit 0
