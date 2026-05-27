# Codex workspace bootstrap template

A two-file template that wires Codex CLI into a workspace with the playbook's hooks (code-review-graph, human-html, deny-edits-in-readonly-dir) and the agent-memory-bridge MCP. Lets a fresh teammate stand up the same Codex experience the author has, in one customize-and-symlink step.

## What it does for the user

When you set up a new workspace on a fresh machine, Codex needs to know:
1. Which hooks run on which tool calls (PreToolUse, PostToolUse, SessionStart).
2. Which MCP servers are registered and how to launch them.
3. Which sandbox + feature toggles to enable.

The two template files in this directory cover items (1), (2), and (3). After customization, the user copies them to `~/.codex/hooks.json` and into the `[mcp_servers.*]` block of `~/.codex/config.toml`, then Codex restarts and the workspace is wired.

## Files

| File | Lands at | Role |
|---|---|---|
| `hooks.json.template` | `~/.codex/hooks.json` (replace whole file) | PreToolUse, PostToolUse, SessionStart hook routing. |
| `config.toml.template` | Merged into `~/.codex/config.toml` | MCP server registrations + sandbox + features toggles. |

## Sentinels

| Sentinel | What to fill in | Example |
|---|---|---|
| `{{WORKSPACE_ROOT}}` | Absolute path to your workspace root. | `/Users/you/work/myteam-workspace` |
| `{{AGENT_SHARED_VENV}}` | Absolute path to a Python venv where MCP servers are installed (typically `~/.config/agent-shared/.venvs/mcp-python`). | `/Users/you/.config/agent-shared/.venvs/mcp-python` |

## How to customize

```bash
# 1. Copy templates into your real config paths.
mkdir -p ~/.codex
cp profiles/templates/codex-workspace-bootstrap/hooks.json.template ~/.codex/hooks.json
# (config.toml is merged, not replaced; open the template and copy the
# [mcp_servers.*] blocks you want into ~/.codex/config.toml manually.)

# 2. Replace sentinels in the copied files.
sed -i.bak \
  -e "s|{{WORKSPACE_ROOT}}|$HOME/work/myteam-workspace|g" \
  -e "s|{{AGENT_SHARED_VENV}}|$HOME/.config/agent-shared/.venvs/mcp-python|g" \
  ~/.codex/hooks.json

# 3. Verify Codex picks up the change.
codex --debug 2>&1 | head -40
```

## Prerequisites

This template assumes you have:
- A workspace dir with `.codex/hooks/` containing the hooks named in `hooks.json` (the playbook's `hooks/` directory ships portable versions of `code-review-graph-update.sh`, `memory-curator-postwrite.sh`, `human-html-advisory.sh`; the templates for the workspace-specific ones live in `hooks/templates/`).
- A Python venv at `{{AGENT_SHARED_VENV}}` with `fastmcp` installed (per the upstream `~/.config/agent-shared/` layout the user follows; `python3 -m venv ~/.config/agent-shared/.venvs/mcp-python && ~/.config/agent-shared/.venvs/mcp-python/bin/pip install fastmcp` will get you started).
- `code-review-graph` installed via `uvx` or homebrew (the SessionStart hook tries `/opt/homebrew/bin/code-review-graph status` and tolerates missing binaries).

## When NOT to use this template

- You're not on macOS (the launchd / homebrew assumptions in some hooks will need adaptation).
- You don't run any of the playbook's hooks (`hooks.json` is then better authored fresh).
- You don't use Codex (this template is Codex-specific; Claude Code and Cursor have their own native config locations covered by the playbook installer directly).

## Provenance

Distilled from `team_LLM_Systems/.codex/{hooks.json,config.toml}` during the v0.2 harness import pass. The original runs today on the author's machine wiring Codex into a workspace with the agent-memory-bridge MCP and a 6-hook chain.
