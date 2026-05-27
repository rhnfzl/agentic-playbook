#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PostToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|NotebookEdit
# Lint guard: run the project's linter on the file just edited.
# Auto-detects ruff / black / eslint / biome / prettier from config files.
#
# Wire as PostToolUse hook for Edit/Write tool calls. Per-file scope (fast).
# A full-project lint runs separately via pre-commit / pre-push gates.

set -u

FILE="${CLAUDE_TOOL_INPUT_FILE_PATH:-${1:-}}"

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
    exit 0  # nothing to lint
fi

# Detect project linter via config files in the file's directory tree
PROJECT_ROOT=$(dirname "$FILE")
while [[ "$PROJECT_ROOT" != "/" ]]; do
    if [[ -f "$PROJECT_ROOT/pyproject.toml" || -f "$PROJECT_ROOT/package.json" || -f "$PROJECT_ROOT/.git" ]]; then
        break
    fi
    PROJECT_ROOT=$(dirname "$PROJECT_ROOT")
done

run_python_lint() {
    if grep -q "tool.ruff" "$PROJECT_ROOT/pyproject.toml" 2>/dev/null; then
        ( cd "$PROJECT_ROOT" && ruff check --fix "$FILE" 2>&1 | tail -5 )
        ( cd "$PROJECT_ROOT" && ruff format "$FILE" 2>&1 | tail -3 )
    elif [[ -f "$PROJECT_ROOT/.flake8" ]]; then
        ( cd "$PROJECT_ROOT" && flake8 "$FILE" 2>&1 | tail -5 )
    fi
}

run_js_lint() {
    if [[ -f "$PROJECT_ROOT/biome.json" ]]; then
        ( cd "$PROJECT_ROOT" && npx @biomejs/biome check --apply "$FILE" 2>&1 | tail -5 )
    elif [[ -f "$PROJECT_ROOT/eslint.config.js" || -f "$PROJECT_ROOT/.eslintrc.json" ]]; then
        ( cd "$PROJECT_ROOT" && npx eslint --fix "$FILE" 2>&1 | tail -5 )
    fi
}

case "$FILE" in
    *.py)   run_python_lint ;;
    *.ts|*.tsx|*.js|*.jsx)  run_js_lint ;;
    *)      ;; # unknown extension; skip
esac

exit 0
