#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# PLAYBOOK-HOOK-MATCHER: Bash
# Pre-push guard: refuse to push to develop / main / master / release/* / hotfix/*.
# Wire as PreToolUse hook for Bash tool calls matching `git push`.
#
# Input sources (in priority order):
#   1. JSON payload on stdin (Claude Code hook contract: tool_input.command)
#   2. CLAUDE_TOOL_INPUT_COMMAND env var (Codex hook contract / manual override)
#   3. argv $1 (direct invocation / tests)
#
# Parses the destination refs out of the push command. Handles:
#   git push                               (uses current branch)
#   git push origin HEAD                   (HEAD resolves to current branch)
#   git push origin develop                (positional ref)
#   git push origin HEAD:develop           (src:dst refspec)
#   git push origin feat/x:develop         (src:dst refspec)
#   git push origin +HEAD:refs/heads/develop  (force-refspec, refs/heads/ prefix)
#   git push --force-with-lease origin develop  (flags skipped)
#
# Allows `git push origin --delete <protected>` (deletion is a different intent).

set -u

# Source 1: stdin (Claude Code hook contract). Only read when stdin is a pipe
# (not a terminal). Claude Code's hook contract closes stdin after sending JSON,
# so cat returns immediately. If stdin is a terminal (manual invocation),
# [ ! -t 0 ] is false and we skip the read entirely, no hang risk.
STDIN_PAYLOAD=""
if [ ! -t 0 ]; then
    STDIN_PAYLOAD=$(cat 2>/dev/null || true)
fi

CMD=""

# Try to extract command from stdin JSON (Claude Code PreToolUse payload).
if [ -n "$STDIN_PAYLOAD" ]; then
    # Prefer python (always present); fall back to jq if available; otherwise grep.
    if command -v python3 >/dev/null 2>&1; then
        CMD=$(printf '%s' "$STDIN_PAYLOAD" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('command', ''))
except Exception:
    pass
" 2>/dev/null || true)
    elif command -v jq >/dev/null 2>&1; then
        CMD=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.tool_input.command // ""' 2>/dev/null || true)
    fi
fi

# Source 2: env var fallback (Codex contract / explicit override).
if [ -z "$CMD" ]; then
    CMD="${CLAUDE_TOOL_INPUT_COMMAND:-}"
fi

# Source 3: argv fallback (direct invocation / tests).
if [ -z "$CMD" ]; then
    CMD="${1:-}"
fi

if [ -z "$CMD" ]; then
    exit 0
fi

if ! echo "$CMD" | grep -qE '^[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
    exit 0
fi

# Allow explicit deletions; user is removing a branch, not adding commits to it.
if echo "$CMD" | grep -qE '(^|[[:space:]])(--delete|-d)([[:space:]]|$|=)'; then
    exit 0
fi

read -ra ARGS <<< "$CMD"

PUSH_IDX=-1
for i in "${!ARGS[@]}"; do
    if [ "${ARGS[$i]}" = "push" ]; then
        PUSH_IDX=$i
        break
    fi
done

if [ "$PUSH_IDX" -lt 0 ]; then
    exit 0
fi

# Resolve HEAD to current branch name. Codex P2 #2: `git push origin HEAD`
# pushes the current branch to a remote ref of the same name; if we leave
# DEST as literal "HEAD" the protected-branch regex never matches.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)

DESTS=()
POSITIONAL_INDEX=0
for ((i = PUSH_IDX + 1; i < ${#ARGS[@]}; i++)); do
    tok="${ARGS[$i]}"
    case "$tok" in
        -*) continue ;;
    esac
    POSITIONAL_INDEX=$((POSITIONAL_INDEX + 1))
    if [ "$POSITIONAL_INDEX" -eq 1 ]; then
        continue
    fi
    case "$tok" in
        *:*) DEST="${tok##*:}" ;;
        *)   DEST="$tok" ;;
    esac
    DEST="${DEST#+}"
    DEST="${DEST#refs/heads/}"
    # Resolve a literal HEAD destination to the current branch (Codex P2 #2).
    if [ "$DEST" = "HEAD" ] && [ -n "$CURRENT_BRANCH" ]; then
        DEST="$CURRENT_BRANCH"
    fi
    DESTS+=("$DEST")
done

if [ "$POSITIONAL_INDEX" -lt 2 ]; then
    if [ -n "$CURRENT_BRANCH" ]; then
        DESTS+=("$CURRENT_BRANCH")
    fi
fi

if [ "${#DESTS[@]}" -eq 0 ]; then
    exit 0
fi

PROTECTED_REGEX='^(develop|main|master|release/.+|hotfix/.+)$'
BLOCKED_REF=""
for dest in "${DESTS[@]}"; do
    if [[ "$dest" =~ $PROTECTED_REGEX ]]; then
        BLOCKED_REF="$dest"
        break
    fi
done

if [ -z "$BLOCKED_REF" ]; then
    exit 0
fi

cat >&2 <<EOF
[never-push-to-develop] Denied: push targets protected ref '$BLOCKED_REF'.

Per rules/never-push-to-develop.md, all changes go through PR review.
Create a feature branch first:

    git checkout -b feat/your-feature-name
    git push -u origin feat/your-feature-name

Then open a PR in VCS.

If this is a true emergency hotfix during an incident, override by setting:
    PLAYBOOK_OVERRIDE_PUSH_GUARD=1 git push ...
and immediately open a follow-up PR back to develop within 24 hours.
EOF

if [ "${PLAYBOOK_OVERRIDE_PUSH_GUARD:-0}" = "1" ]; then
    echo "[never-push-to-develop] PLAYBOOK_OVERRIDE_PUSH_GUARD set; allowing push." >&2
    exit 0
fi

exit 2
