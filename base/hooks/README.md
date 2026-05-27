# Hooks

This directory holds shareable shell hooks that the installer wires into each coding agent's hook surface. Hooks fire on agent events (before a tool call, after a file edit, on session stop) and either gate the action or do work alongside it.

## What a hook is

A hook is a shell script that runs in response to a specific lifecycle event. Different from skills (which the agent loads when relevant) and rules (which are always-on instructions). Hooks are enforcement: the agent does not choose to invoke them; the harness does.

Common Claude-shaped events:
- **PreToolUse**: fires before the agent executes a tool call (Bash, Edit, etc.). Can deny by exiting nonzero (exit 2 = deny on Claude).
- **PostToolUse**: fires after a tool call succeeds. Used for logging, auto-indexing, follow-up work.
- **SessionStart**: fires once when a coding-agent session begins. Used for session-brief, context loading.
- **Stop**: fires when the agent's main loop finishes a turn or the user exits a session.

Cursor uses camelCase variants (`preToolUse`, `postToolUse`, `sessionStart`, `stop`); Windsurf Cascade uses a snake_case 12-event model (`pre_run_command`, `pre_write_code`, `post_write_code`, etc.). The installer translates per adapter, so hook authors write one Claude-shaped script.

## Three layers (per ADR-0036)

A hook author edits one file, but the agent runtime sees three different copies of "the hook" before it fires. If any of the three goes out of sync, the agent silently skips the hook with no error in the install lockfile. This section is the contract every hook author and reviewer should hold up against any hook problem; the per-layer debug checklist below is the order to walk it in when a hook is not firing.

In product terms: "I added a hook" only matters once the agent actually runs it on the right tool call. ADR-0036 makes that contract machine-checkable.

| Layer | What it is for hooks | Verified by |
|---|---|---|
| 1. Canonical source | The author's edit. Either `hooks/<name>.sh` (orphan) or `skills/<cat>/<skill>/hooks/<name>.sh` (skill-owned), with the matching root path a symlink. | `make check` (the `hook-source-unification` gate) |
| 2. Materialization | What the installer writes. `~/.claude/hooks/<name>.sh`, `~/.codex/hooks/<name>.sh`, `~/.cursor/hooks/<name>.sh`, `~/.codeium/windsurf/hooks/<name>.sh`, project `.github/hooks/<name>.sh`. Lockfile records every path. | `make status` and the lifecycle test suite |
| 3. Runtime discovery | The adapter's native config entry that makes the agent actually fire the hook. `~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.cursor/hooks.json`, `~/.cline/hooks.json`, project `.github/hooks.json`, `~/.codeium/windsurf/hooks.json`. | `make doctor-verify` and `test_native_hook_config_after_install` |

A change is not "done" until layer 3 is verified. Lockfile alone is not enough; a registered command path that does not exist in the agent's native config will never fire even though `make status` reports clean.

### Hook not firing? Three-layer debug checklist

If a hook you expected to fire did not, walk these in order:

1. **Layer 1**: is the canonical source on disk and well-formed? `cat hooks/<name>.sh` and verify both `PLAYBOOK-HOOK-EVENT` and `PLAYBOOK-HOOK-MATCHER` are present. Run `make check` and confirm the `hook-source-unification` and `hook-metadata` gates pass.
2. **Layer 2**: did the installer copy the script to the adapter's hooks dir? `ls ~/.claude/hooks/<name>.sh` (or `~/.codex/hooks/`, `~/.cursor/hooks/`, `~/.codeium/windsurf/hooks/`, etc.). If missing, run `make install` and re-check.
3. **Layer 3a**: does the adapter's native config contain an entry pointing at the materialized path? `cat ~/.cursor/hooks.json | jq '.hooks'` (or the adapter's equivalent). If the file or the entry is absent, the agent never loads the hook.
4. **Codex-specific**: did the hook need PreToolUse + non-Bash auto-promote? Inspect `~/.codex/hooks.json` for the hook under `PostToolUse` (not `PreToolUse`) for any matcher other than `Bash`. The installer auto-promotes; Codex's `PreToolUse` only reliably intercepts `Bash` per OpenAI's 2026 docs.
5. **Cursor-specific**: when the hook declared `PLAYBOOK-HOOK-CURSOR-WRAPPER: <wrapper>.sh`, confirm the WRAPPER (not the core) is the entry under `preToolUse` in `~/.cursor/hooks.json`. Cursor registers the wrapper and the wrapper invokes the core as a sibling.
6. **Windsurf-specific**: the command in `~/.codeium/windsurf/hooks.json` (or project `.windsurf/hooks.json`) must take the form `<.../hooks/_cascade-translate.sh> <.../hooks/<name>.sh>`. The translator re-encodes Cascade `tool_info` stdin to Claude `tool_input` shape; without it, the core hook gets the wrong JSON.
7. **Runtime**: did the agent restart after the install? Some agents cache settings.json at session start; a hook added mid-session does not fire until a new session.

`make doctor-verify` walks layers 2 + 3 automatically and prints the exact `cat <path>` command for any drift it finds.

## Canonical source unification

Hooks that have a skill owner live with the skill in `skills/<category>/<skill>/hooks/`. Root `hooks/<name>.sh` becomes a symlink to the skill-owned canonical. Orphan hooks (no skill owner) keep their canonical home at the root.

Current layout:

| Hook | Canonical source | Root path |
|---|---|---|
| `human-html-advisory.sh` | `skills/meta/human-html/hooks/` | symlink |
| `human-html-autoindex.sh` | `skills/meta/human-html/hooks/` | symlink |
| `human-html-advisory-cursor.sh` | `skills/meta/human-html/hooks/` | symlink (CURSOR-ONLY) |
| `lint-guard.sh` | `hooks/` | canonical |
| `never-push-to-develop.sh` | `hooks/` | canonical |
| `code-review-graph-update.sh` | `hooks/` | canonical |
| `memory-curator-postwrite.sh` | `hooks/` | canonical |
| `agent-memory-session-brief.sh` | `hooks/` | canonical |
| `sonar-advisory.sh` | `hooks/` | canonical |
| `anchored-fs-pretool-edit.sh` | `hooks/` | canonical (ADAPTERS: claude-code; wraps Python implementation in `mcp/anchored-fs/`) |
| `anchored-fs-posttool-read.sh` | `hooks/` | canonical (ADAPTERS: claude-code; wraps Python implementation in `mcp/anchored-fs/`) |
| `_cascade-translate.sh` | `hooks/` | helper (Windsurf translator wrapper; NOT a hook) |

## What ships in this directory

| Hook | Event | What it does |
|---|---|---|
| `never-push-to-develop.sh` | PreToolUse (Bash) | Refuses `git push` to develop/main/master/release-*/hotfix-*. Honors `PLAYBOOK_OVERRIDE_PUSH_GUARD=1` for incident escape hatch. |
| `lint-guard.sh` | PostToolUse (Edit/Write) | Runs the project's linter on the file just edited. Detects ruff/black/eslint/biome/prettier via config files. |
| `sonar-advisory.sh` | PostToolUse (Edit/Write) | Advisory check against code-quality quality gate. Hits team code-quality via VPN; warns on drift, does not block. |
| `human-html-autoindex.sh` | PostToolUse (Edit/Write/Bash) | Regenerates `docs/human-html/index.html` whenever a new artifact lands. Probes Claude/Codex/Cursor/Windsurf skill install paths to find `human_html_artifacts.py`. |
| `human-html-advisory.sh` | PreToolUse (Edit/Write) | Advisory nudge toward HTML when an HIL-shaped Markdown write is about to land outside the agreed Markdown lanes. Generic across harnesses. |
| `human-html-advisory-cursor.sh` | PreToolUse (Cursor only) | Cursor wrapper that re-encodes the core advisory's stderr output as `{permission:"allow", agent_message:"..."}` JSON on stdout per Cursor's hook contract. |
| `code-review-graph-update.sh` | PostToolUse (Edit/Write/Bash) | Refreshes the code-review-graph embeddings. No-op when binary isn't installed. |
| `memory-curator-postwrite.sh` | PostToolUse (Edit/Write) | Enforces a hard line cap on the workspace's `MEMORY.md` by demoting low-priority entries to `MEMORY_ARCHIVE.md`. |
| `agent-memory-session-brief.sh` | SessionStart | Renders a short opener from accumulated memory by calling `agent_memory_bridge.py context`. Always exits 0. |

### Templates (workspace-specific scaffolds)

Hooks under `hooks/templates/` are NOT installed by `make install`. They are scaffolds with `{{SENTINEL}}` placeholders for patterns that depend on workspace-specific values. See `hooks/templates/CUSTOMIZE.md`.

| Template | What it does |
|---|---|
| `deny-edits-in-readonly-dir.sh.template` | Denies Edit / Write / MultiEdit / NotebookEdit on a directory you mirror from upstream. |

## How the installer wires hooks

| Adapter | Hook destination | Registration file | Shape |
|---|---|---|---|
| `claude_code` | `~/.claude/hooks/<name>.sh` | `~/.claude/settings.json` | PascalCase events, nested `{hooks:[{type,command}], matcher}` |
| `codex` | `~/.codex/hooks/<name>.sh` | `~/.codex/hooks.json` | PascalCase events, Claude-compatible. **Auto-promotes PreToolUse + non-Bash matcher to PostToolUse** (per OpenAI: PreToolUse reliably intercepts only Bash). |
| `cursor` | `~/.cursor/hooks/<name>.sh` + project `.cursor/hooks/` | `~/.cursor/hooks.json` + project | camelCase events, flat `{command, matcher, timeout}` per entry, snake_case JSON stdout responses. |
| `cline` | `~/.cline/hooks/<name>.sh` | `~/.cline/hooks.json` | PascalCase Claude-compat (Cline v3.36+). |
| `copilot` | project `.github/hooks/<name>.sh` | project `.github/hooks.json` | PascalCase Claude-compat (VS Code Insiders preview). |
| `windsurf` | user `~/.codeium/windsurf/hooks/` + project `.windsurf/hooks/` | both `hooks.json` paths | snake_case Cascade events. Each entry shaped `{command: "<translator> <core>"}` so the shared `_cascade-translate.sh` wrapper bridges Cascade `tool_info` stdin to Claude-shaped `tool_input`. |
| `aider` / `gemini_cli` / `pi` / Tier 3 | n/a | n/a | No documented shell-hook surface. |

The adapters read the event from explicit headers near the top of each hook script (per ADR-0027 + ADR-0034). Filename-based inference is a deprecated fallback retained for back-compat.

Header conventions:

```bash
#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse                              # required
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|NotebookEdit     # required (or '*')
# PLAYBOOK-HOOK-CURSOR-MATCHER: Edit|Write|...|StrReplace      # optional Cursor override
# PLAYBOOK-HOOK-CURSOR-WRAPPER: human-html-advisory-cursor.sh  # optional Cursor wrapper
# PLAYBOOK-HOOK-CURSOR-ONLY: true                              # optional: skip non-Cursor adapters
# PLAYBOOK-HOOK-ADAPTERS: claude-code,codex                    # optional: restrict to these adapter slugs
# PLAYBOOK-HOOK-WINDSURF-EVENT: post_setup_worktree            # optional Windsurf event pin
```

`PLAYBOOK-HOOK-ADAPTERS` (per ADR-0037) generalizes `CURSOR-ONLY` and pins a hook to one or more specific adapter slugs (`claude-code`, `codex`, `cursor`, `cline`, `copilot`, `windsurf`). When unset, the hook installs to every hook-capable adapter (modulo `CURSOR-ONLY`). The anchored-fs wrappers (`hooks/anchored-fs-*.sh`) use `ADAPTERS: claude-code` because their Python implementation only parses Claude Code's hook payload shape.

Auto-derive rules (when override headers are absent):

- **Cursor matcher** = Claude matcher with `Bash -> Shell` and `StrReplace` appended to Edit-family matchers.
- **Cursor event** = Claude event lowercased camelCase mapping (`PreToolUse -> preToolUse`).
- **Codex event** = same as Claude, except PreToolUse + non-Bash matcher promotes to PostToolUse.
- **Windsurf event** = derived from PreToolUse/PostToolUse + matcher token family: Bash-family -> `pre/post_run_command`, Edit-family -> `pre/post_write_code`. SessionStart -> `post_setup_worktree`, Stop -> `post_cascade_response`. Mixed matchers register under both event branches.

## How to write a hook

Hooks are shell scripts. Inputs and outputs depend on the harness:

**Claude Code PreToolUse / PostToolUse contract:**
- Input: JSON on stdin like `{"tool_input": {"command": "git push origin develop"}, "cwd": "..."}`. Read with `cat`.
- Output: stderr for human messages, exit code 0 = allow, exit code 2 = deny (PreToolUse only).
- Env: `CLAUDE_PROJECT_DIR`, `$HOME`.

**Cursor PreToolUse contract:**
- Input: JSON on stdin (Cursor sends `tool_input.path` for StrReplace alongside `file_path` for Edit/Write).
- Output: snake_case JSON on stdout like `{"permission":"allow","agent_message":"hint..."}`. permission is REQUIRED. camelCase is ignored. To deny: `{"permission":"deny","user_message":"..."}` + exit 2.
- Env: `CURSOR_PROJECT_DIR`.
- See `human-html-advisory-cursor.sh` for the wrapper pattern that re-encodes a stderr-based hook as Cursor-shaped JSON.

**Codex hook contract:**
- Same JSON-on-stdin shape as Claude.
- PreToolUse fires reliably ONLY for `Bash`; Edit/Write hooks should be PostToolUse (the installer auto-promotes).
- Output: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"|"deny"}}` on stdout for blocking decisions; stderr is surfaced to the model otherwise.

**Windsurf Cascade contract:**
- Input: Cascade stdin `{agent_action_name, trajectory_id, ..., tool_info: {command_line/file_path/...}}`.
- Output: exit code 2 (pre-hooks) blocks the action and surfaces stderr. Post-hooks can't block.
- The playbook's `_cascade-translate.sh` wrapper translates Cascade stdin to Claude-shaped stdin so playbook hooks run unchanged.

## Cursor reliability caveats (per Cursor forum, May 2026)

- `postToolUse.additional_context` is DISCARDED for non-MCP tools. Only `sessionStart` reliably injects context into the agent's system prompt. Do not rely on postToolUse to deliver agent-visible context; use stderr (Claude-shaped) or `sessionStart` instead.
- `deny` may not block reads in all Cursor builds. Use `.cursorignore` for hard read protection.
- Non-UTF-8 Windows locales may double-encode non-ASCII characters on the stdin pipe. Use PowerShell 7 or enable system UTF-8 to avoid.
- Cursor CLI (`cursor-agent`) fires `beforeShellExecution`/`afterShellExecution` reliably but several IDE lifecycle hooks (additional_context, some shell-side variants) are flaky.

## Codex semantic caveats

- PreToolUse RELIABLY intercepts only Bash. `apply_patch` and MCP tools are in the schema but unreliable per the 2026 OpenAI docs. Edit/Write fire ONLY PostToolUse.
- The installer auto-promotes PreToolUse + non-Bash matcher to PostToolUse so your hook still fires.
- `[features].codex_hooks = true` is the default. No opt-in required.

## How to add a new hook

1. Decide canonical home: with a skill (under `skills/<cat>/<skill>/hooks/`) or at the root (`hooks/`).
2. Create the script with shebang, PLAYBOOK-HOOK-EVENT + PLAYBOOK-HOOK-MATCHER headers, and the logic.
3. Read input from stdin (preferred) with env-var and argv fallbacks for testability.
4. Use exit code 2 to deny (PreToolUse Claude/Codex/Cline/Copilot); exit code 0 = allow.
5. If you need Cursor-specific output (JSON `agent_message`), author a `<name>-cursor.sh` wrapper with `PLAYBOOK-HOOK-CURSOR-ONLY: true` and add `PLAYBOOK-HOOK-CURSOR-WRAPPER: <wrapper>.sh` to the core.
6. Test against all harnesses you target: pipe Claude-shape stdin, Cursor-shape stdin, Cascade-shape stdin.
7. Run `make check` (covers em-dash lint + hook metadata).
8. PR per `CONTRIBUTING.md`.

## Quality bar

- A hook does ONE thing well. Multi-purpose hooks split into separate files.
- A hook is SAFE to fail. If a sub-command crashes, the hook exits 0 with a warning, NOT a block.
- A hook respects override env vars (e.g., `PLAYBOOK_OVERRIDE_PUSH_GUARD=1`) so users can escape during incidents.
- A hook reads input from ALL three sources (stdin, env, argv) so it works under Claude / Codex / Cursor / Windsurf / Cline / Copilot and manual testing.

## References

- [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks) (Claude Code hook contract)
- [developers.openai.com/codex/hooks](https://developers.openai.com/codex/hooks) (Codex hook surface)
- [cursor.com/docs/hooks](https://cursor.com/docs/hooks) (Cursor hook surface)
- [docs.windsurf.com/windsurf/cascade/hooks](https://docs.windsurf.com/windsurf/cascade/hooks) (Windsurf Cascade hooks)
- ADR-0027 (PLAYBOOK-HOOK-EVENT header + agents-md document type)
- ADR-0029 (hook reconciliation + matcher header)
- ADR-0034 (cross-agent hook contract)
- ADR-0035 (canonical hook source: skill-owned vs root)
- `rules/never-push-to-develop.md` (rule that motivates `never-push-to-develop.sh`)
