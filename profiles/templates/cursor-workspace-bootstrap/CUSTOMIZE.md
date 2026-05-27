# Cursor workspace bootstrap template

A three-file template that wires Cursor IDE (and CLI) into a workspace with the playbook's hooks (lint-guard, human-html advisory + autoindex, never-push-to-develop, code-review-graph-update, session brief) and the agent-memory-bridge + anchored-fs MCP servers. Lets a fresh teammate stand up the same Cursor experience the author has, in one customize-and-symlink step.

## What this does for the user

When you set up a new workspace on a fresh Mac with Cursor installed, Cursor needs to know:
1. Which hooks fire on which tool calls (preToolUse, postToolUse, sessionStart). Cursor uses camelCase events, snake_case JSON stdout responses, and the matcher tokens differ slightly from Claude (Shell instead of Bash; StrReplace alongside Edit/Write/MultiEdit).
2. Which MCP servers are registered and how to launch them.
3. Where the project root sits ($CURSOR_PROJECT_DIR) so workspace-aware hooks like human-html-advisory can resolve their allowlist.

The two template files below cover items (1) and (2). After customization, the user copies them to `~/.cursor/hooks.json` and `~/.cursor/mcp.json` (or the project-level `.cursor/` if a single repo is the target).

## Files

| File | Lands at | Role |
|---|---|---|
| `hooks.json.template` | `~/.cursor/hooks.json` (user) or `<workspace>/.cursor/hooks.json` (project) | preToolUse / postToolUse / sessionStart hook routing in cursor-shaped JSON. |
| `mcp.json.template` | `~/.cursor/mcp.json` (user) or `<workspace>/.cursor/mcp.json` (project) | MCP server registrations (agent-memory-bridge, anchored-fs). |

## Sentinels

| Sentinel | What to fill in | Example |
|---|---|---|
| `{{WORKSPACE_ROOT}}` | Absolute path to your workspace root. | `/Users/you/work/myteam-workspace` |
| `{{AGENT_SHARED_VENV}}` | Absolute path to a Python venv where MCP servers are installed. Typically `~/.config/agent-shared/.venvs/mcp-python`. | `/Users/you/.config/agent-shared/.venvs/mcp-python` |
| `{{AGENT_SHARED_MCP_ROOT}}` | Absolute path to the playbook-symlinked MCP source root. Typically `~/.config/agent-shared/mcp_servers`. | `/Users/you/.config/agent-shared/mcp_servers` |

## How to customize

```bash
# 1. Copy templates into your real config paths.
mkdir -p ~/.cursor
cp profiles/templates/cursor-workspace-bootstrap/hooks.json.template ~/.cursor/hooks.json
cp profiles/templates/cursor-workspace-bootstrap/mcp.json.template ~/.cursor/mcp.json

# 2. Replace sentinels.
sed -i.bak \
  -e "s|{{WORKSPACE_ROOT}}|$HOME/work/myteam-workspace|g" \
  -e "s|{{AGENT_SHARED_VENV}}|$HOME/.config/agent-shared/.venvs/mcp-python|g" \
  -e "s|{{AGENT_SHARED_MCP_ROOT}}|$HOME/.config/agent-shared/mcp_servers|g" \
  ~/.cursor/hooks.json ~/.cursor/mcp.json

# 3. Verify Cursor picks up the change by restarting and looking at:
#    Cursor -> Settings -> Hooks (UI shows registered hooks per event)
```

For PROJECT-level (per-repo) install: replace `~/.cursor` with `<workspace>/.cursor` and Cursor will scope these hooks/MCP to that workspace only.

## Cursor-specific behavior notes (per cursor.com/docs/hooks + 2026 testing)

- **JSON output is snake_case**: hooks emit `{permission: "allow"|"deny"|"ask", agent_message?, user_message?, updated_input?}` on stdout. camelCase variants (agentMessage, etc.) are ignored.
- **Advisory hooks need the wrapper pattern**: the playbook ships `human-html-advisory-cursor.sh` which wraps the core stderr-based hook and emits Cursor-shaped JSON. Other adapters skip this wrapper via the `PLAYBOOK-HOOK-CURSOR-ONLY: true` header.
- **`postToolUse.additional_context` is unreliable**: per Cursor forum bug reports through May 2026, only `sessionStart` reliably injects context into the agent. Treat postToolUse hooks as audit/logging only, not context-injection.
- **Tool name aliases**: Cursor's shell tool is `Shell` (not `Bash`); its surgical-edit tool is `StrReplace`. The playbook's hook headers include `PLAYBOOK-HOOK-CURSOR-MATCHER` overrides where the auto-derive (Bash -> Shell; append StrReplace to edit-family matchers) is insufficient.
- **CLI vs IDE parity caveat**: `cursor-agent` (the CLI) fires `beforeShellExecution`/`afterShellExecution` reliably, but several IDE lifecycle hooks (additional_context injection, some shell-side variants) are flaky. Do not depend on advisory output reaching the model from postToolUse; use stderr + sessionStart instead.

## Prerequisites

This template assumes you have:
- A workspace dir with `.cursor/hooks/` containing the hooks named in `hooks.json`. The playbook installer drops these in for you when you run `make install` and select cursor; this template documents the shape for fresh / non-installer setups.
- A Python venv at `{{AGENT_SHARED_VENV}}` with `fastmcp` installed (`python3 -m venv ~/.config/agent-shared/.venvs/mcp-python && ~/.config/agent-shared/.venvs/mcp-python/bin/pip install fastmcp`).
- MCP source bundles symlinked under `{{AGENT_SHARED_MCP_ROOT}}` by the playbook installer, including `agent-memory-bridge/agent_memory_mcp.py` and `anchored-fs/server.py`.
- `code-review-graph` installed via `uvx` or homebrew (the session-brief / postToolUse hooks tolerate it being missing).
- Cursor 2.0.64+ (the snake_case advisory JSON contract). Older Cursor builds will silently ignore the `agent_message` field.

## When NOT to use this template

- You're using Cursor on Windows (the `bash` shebang in the hook scripts won't run; you'd need PowerShell-compatible variants).
- You don't use any of the playbook's hooks (`hooks.json` is then better authored fresh).
- You use Claude Code or Codex but not Cursor (the Claude-shaped template in `profiles/templates/codex-workspace-bootstrap/` covers PascalCase + Claude/Codex semantics).

## Provenance

Distilled from the manual `team_LLM_Systems/.cursor/{hooks.json,mcp.json}` wiring during the v0.6 multi-agent hook parity work. The original runs today on the author's machine; this template captures the shape so the playbook can scaffold equivalent Cursor setups for new workspaces and new teammates.
