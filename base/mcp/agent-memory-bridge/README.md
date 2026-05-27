# agent-memory-bridge MCP

Local shared memory bridge that lets multiple coding agents (Claude Code, Codex, Cursor) read and write the same per-workspace memory pool, plus a co-located CLI curator that caps the index size.

## What it does for the user

When you work across Claude Code and Codex sessions on the same project, each tool has its own memory. The bridge gives them ONE shared SQLite-backed memory store so a note you saved in Claude this morning is visible to Codex this afternoon. The curator keeps the `MEMORY.md` index under a hard line cap (default 200) by demoting low-priority entries to `MEMORY_ARCHIVE.md`, so the index stays scannable as the memory pool grows.

## Files in this bundle

| File | Role |
|---|---|
| `agent_memory_bridge.py` | SQLite-backed memory store + CLI (`add`, `search`, `recent`, `audit`). |
| `agent_memory_mcp.py` | FastMCP wrapper exposing `memory_search`, `memory_context`, `memory_propose`, `memory_audit` tools. |
| `memory_curator.py` | CLI that caps `MEMORY.md` line count and archives demoted entries to `MEMORY_ARCHIVE.md`. Invoked by the `memory-curator-postwrite.sh` hook. |
| `server.json` | MCP transport config (stdio). Uses `{{AGENT_SHARED_MCP_DIR}}` placeholder; the playbook installer expands it to the symlink target. |

## How it gets distributed

The playbook installer (`scripts/install.py`) handles this in two steps:

1. **Source materialization** (`_loader.materialize_mcp_sources`): symlinks `agent_memory_bridge.py`, `agent_memory_mcp.py`, `memory_curator.py` from `mcp/agent-memory-bridge/` in the playbook repo to `~/.config/agent-shared/mcp_servers/agent-memory-bridge/`. Re-installable: existing correct symlinks are left alone; mismatched symlinks are updated; real (non-symlink) files at the target are never overwritten.
2. **Config registration** (per-adapter MCP wiring): writes a `[mcp_servers.agent-memory-bridge]` entry into each enabled agent's MCP config (`~/.codex/config.toml`, `~/.claude.json`, Cursor's mcp.json, etc.), with the `{{AGENT_SHARED_MCP_DIR}}` placeholder expanded to the resolved symlink target.

This composes with the user's existing `~/.config/agent-shared/sync_mcp_configs.py` (which distributes the registration block from `mcp_servers.json` to Claude and Codex globally). The playbook installer writes registration directly per-agent; `sync_mcp_configs.py` can additionally be re-run to refresh global registrations from the shared source.

## Configuration knobs (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_MEMORY_WORKSPACE` | `$CLAUDE_PROJECT_DIR` → `$CODEX_WORKSPACE` → `cwd` | Workspace root used to derive per-workspace state paths. |
| `AGENT_MEMORY_DB` | `<workspace>/.agent-harness/memory/memory.sqlite` | SQLite store path. |
| `AGENT_MEMORY_CLAUDE_DIGEST` | `<workspace>/.codex/memory/claude-memory-import.md` | Markdown digest written for Codex sessions. |
| `AGENT_MEMORY_CLAUDE_DIRS` | (auto-discover) `glob ~/.claude/projects/*/memory` | Colon-separated explicit list of Claude memory dirs the bridge ingests from. |
| `MEMORY_INDEX_DIR` | (auto-derive from `CLAUDE_PROJECT_DIR`) | Memory dir the curator targets. |
| `MEMORY_CURATOR_CAP` | `200` | Hard line cap the curator enforces on `MEMORY.md`. |

## Manual test

```bash
# Verify symlink layout after install:
ls -la ~/.config/agent-shared/mcp_servers/agent-memory-bridge/

# Smoke-test the MCP locally (stdio, exits after JSON-RPC handshake):
python3 ~/.config/agent-shared/mcp_servers/agent-memory-bridge/agent_memory_mcp.py < /dev/null

# Smoke-test the curator (dry-run audit):
MEMORY_INDEX_DIR=~/.claude/projects/<your-slug>/memory \
  python3 ~/.config/agent-shared/mcp_servers/agent-memory-bridge/memory_curator.py audit
```

## Why bundled, not separate dirs

`memory_curator.py` is a CLI tool, not an MCP server, but it co-locates with the bridge because:
- Both tools target the same `~/.claude/projects/<slug>/memory/` filesystem area.
- The user's upstream setup ships them together in one workspace's `scripts/`.
- Installing both via one symlink target keeps the surface tidy.

The `memory-curator-postwrite.sh` hook resolves `memory_curator.py` from `~/.config/agent-shared/mcp_servers/agent-memory-bridge/memory_curator.py` to match this layout.

## Provenance

Imported from `team_LLM_Systems/scripts/` upstream. Hardcoded workspace paths were replaced with env-var fallback chains so the bridge runs in any workspace the playbook is installed into.
