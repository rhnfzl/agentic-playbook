#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PostToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|Bash
# PostToolUse hook: refresh code-review-graph for repos in the current workspace.
#
# When an Edit/Write/MultiEdit tool lands changes, recompute the code-review-graph
# embeddings so search and review tools see fresh signal. Lock-protected so
# concurrent tool calls coalesce into a single refresh run.
#
# Workspace resolution:
#   $CLAUDE_PROJECT_DIR -> $CODEX_WORKSPACE -> pwd
#
# Repos to refresh, in priority order:
#   1. $CODE_REVIEW_GRAPH_REPOS (colon-separated absolute paths)
#   2. Immediate subdirectories of WORKSPACE_ROOT that are git repos
#   3. The git repo containing $PWD, if not covered above
#
# Exit status: never blocks the upstream tool call. Failures (missing
# code-review-graph binary, repo without .git, update command crash) are logged
# to stderr but the hook ALWAYS exits 0. PostToolUse hooks are best-effort; a
# nonzero exit shows up as a hook failure on every edit on machines that lack
# the optional binary, which would be noisy and useless.
#
# Skips entirely when the inbound tool_name is not a mutating tool. Claude Code
# registers this hook without a matcher, so Read / Grep / Bash would otherwise
# trigger expensive graph refreshes on every interactive turn.

set -u

WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_WORKSPACE:-$(pwd)}}"
LOCK_DIR="$WORKSPACE_ROOT/.code-review-graph-update.lock"
CRG_BIN="${CODE_REVIEW_GRAPH_BIN:-/opt/homebrew/bin/code-review-graph}"

resolve_repos() {
  if [ -n "${CODE_REVIEW_GRAPH_REPOS:-}" ]; then
    printf '%s\n' "$CODE_REVIEW_GRAPH_REPOS" | tr ':' '\n'
    return
  fi
  if [ -d "$WORKSPACE_ROOT" ]; then
    for entry in "$WORKSPACE_ROOT"/*/; do
      [ -d "$entry/.git" ] && printf '%s\n' "${entry%/}"
    done
  fi
}

update_repo() {
  local repo="$1"

  if [ ! -x "$CRG_BIN" ]; then
    CRG_BIN="$(command -v code-review-graph 2>/dev/null || true)"
  fi

  if [ -z "$CRG_BIN" ]; then
    printf 'code-review-graph hook: code-review-graph executable not found\n' >&2
    return 1
  fi

  if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'code-review-graph hook: not a git repo, skipping: %s\n' "$repo" >&2
    return 0
  fi

  printf 'code-review-graph hook: updating %s\n' "$repo" >&2
  (cd "$repo" && "$CRG_BIN" update --skip-flows)
}

acquire_lock() {
  local lock_pid

  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
    return 0
  fi

  if [ ! -r "$LOCK_DIR/pid" ]; then
    printf 'code-review-graph hook: update already running, skipping this hook run\n' >&2
    return 1
  fi

  read -r lock_pid < "$LOCK_DIR/pid" || lock_pid=""
  if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
    printf 'code-review-graph hook: update already running, skipping this hook run\n' >&2
    return 1
  fi

  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true

  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
    return 0
  fi

  printf 'code-review-graph hook: update already running, skipping this hook run\n' >&2
  return 1
}

should_run_for_tool() {
  local input="$1"
  if [ -z "$input" ]; then
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    return 0
  fi
  local tool_name
  tool_name=$(jq -r '.tool_name // empty' <<<"$input")
  if [ -z "$tool_name" ]; then
    return 0
  fi
  case "$tool_name" in
    Edit|Write|MultiEdit|NotebookEdit|apply_patch) return 0 ;;
    *) return 1 ;;
  esac
}

main() {
  local repo
  local repos_handled=0
  local input

  input="$(cat)"

  if ! should_run_for_tool "$input"; then
    return 0
  fi

  if ! acquire_lock; then
    return 0
  fi

  while IFS= read -r repo; do
    [ -n "$repo" ] || continue
    update_repo "$repo" >/dev/null 2>&1 || true
    repos_handled=1
  done < <(resolve_repos)

  if [ "$repos_handled" -eq 0 ]; then
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      repo="$(git rev-parse --show-toplevel)"
      update_repo "$repo" >/dev/null 2>&1 || true
    fi
  fi

  return 0
}

main "$@"
