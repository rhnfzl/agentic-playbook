# Hooks

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Shell hooks that run at agent lifecycle events (PreToolUse, PostToolUse, UserPromptSubmit, etc). They enforce guardrails without involving the agent.

## What Lives Here

- `<hook-name>.sh` executables, POSIX-compatible shell.
- `README.md` enumerates each hook, its trigger, and its return semantics.
- `templates/` for scaffolds when authoring new hooks.

## Local Commands

- Test a hook in isolation: `bash hooks/<name>.sh < test-payload.json`.
- Wire into a workspace via adapter configs in `scripts/adapters/`.

## Edit Rules

- Hooks must always exit cleanly. PostToolUse hooks exit 0 unconditionally (best-effort discipline).
- PreToolUse hooks may exit non-zero to block, but only with a clear stderr message.
- Filter on tool name via `jq -r '.tool_name'` before acting; do not assume every invocation applies.
- Resolve workspace root via `$CLAUDE_PROJECT_DIR`, then `$CURSOR_PROJECT_DIR`, then `$CODEX_WORKSPACE`, then the hook JSON `.cwd`, then `pwd`. The Cursor env var was added with the multi-agent hook parity work; new hooks must honor the full chain.
- Files prefixed with `_` (e.g. `hooks/_cascade-translate.sh`) are adapter-internal helpers, not registered hooks. They are skipped by the loader (`scripts/adapters/_reader.py::load_hooks`) and by the hook-metadata check, and they do not need PLAYBOOK-HOOK-* headers.

## Required Checks

- Shellcheck clean (`shellcheck hooks/*.sh`).
- Hook must declare its tool-name filter at the top.
- No silent failures: errors go to stderr with context.

## Required Skills

- None mandatory. Reference `docs/research/inspirations.md` for hook patterns from other ecosystems.

## Do Not

- Modify files outside the workspace root.
- Call out to network services without a clear timeout.
- Skip `set -e` for "robustness"; explicit error paths are required.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a hook or changing the trigger semantics.
