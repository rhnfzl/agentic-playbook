# 0012. mcp/ bundle directory for locally-hosted Python MCPs

## Status
Accepted (2026-05-25)

## Context

v0.1 and v0.2 shipped MCP configs as flat `mcp/<name>.json` files (one JSON per server). That shape worked for hosted MCPs (Atlassian SSE, Tavily HTTP) and npx-installable MCPs (Slack, VCS) because the JSON only had to record the command and env; the actual server source lived in a published package the user did not host.

The v0.2.1 harness import surfaced a different case: the user's `agent-memory-bridge` MCP is a 900-line Python server (`agent_memory_bridge.py`), a thin FastMCP wrapper (`agent_memory_mcp.py`), and a co-located CLI curator (`memory_curator.py`) maintained alongside the workspace. There is no published package; the source is the source. Two options:

1. Keep the source outside the playbook (in `~/.config/agent-shared/mcp_servers/agent-memory-bridge/` or a separate repo) and let `mcp/agent-memory-bridge.json` only point at the install location. Rejected: source then drifts per-machine, no team-shared updates, no lint coverage, no version control of the MCP behavior itself.

2. Ship the source in the playbook and let the installer place it on the user's machine. Accepted: source lives in `mcp/agent-memory-bridge/` (versioned, lint-checked, distributable); installer symlinks `.py` files to `~/.config/agent-shared/mcp_servers/<name>/`; the registration JSON points at the symlink target so each agent's MCP config (`~/.codex/config.toml`, `~/.claude.json`, etc.) launches the right binary.

## Decision

`mcp/` now supports TWO layouts that coexist:

| Layout | Shape | Use for |
|---|---|---|
| Flat | `mcp/<name>.json` (single JSON file) | Hosted / npx / uvx / docker MCPs where source is not in the playbook (Atlassian, Tavily, Slack, VCS, error-tracking, code-quality, code-review-graph). |
| Bundle | `mcp/<name>/{server.json, *.py, README.md}` (directory) | Locally-hosted Python MCPs whose source is shipped in the playbook (agent-memory-bridge). |

`_loader.load_mcp_configs(repo_root)` discovers both via two passes (`mcp_dir.glob("*.json")` then `mcp_dir.glob("*/server.json")`). Bundle configs carry an additional `source_dir` field on the `McpConfig` NamedTuple that points at `mcp/<name>/` in the playbook checkout; flat configs leave `source_dir=None`.

## Bundle anatomy

```
mcp/<name>/
├── server.json     # MCP registration (command + args + env). Uses {{AGENT_SHARED_MCP_DIR}} placeholder.
├── README.md       # What the MCP does, env vars, manual smoke-test.
├── <name>.py       # Server entry point (or wrapper around a separate implementation).
└── <support>.py    # Any number of supporting .py files (the installer symlinks every .py).
```

Skipped at symlink time: `server.json`, `README.md`, `CUSTOMIZE.md`. Everything else gets a symlink.

## Symlink target

The installer materializes bundled `.py` files to `~/.config/agent-shared/mcp_servers/<name>/` via `_loader.materialize_mcp_sources(mcp_configs)`. The function returns per-link action codes:

| Code | Meaning |
|---|---|
| `created` | New symlink placed at the target. |
| `updated` | Existing symlink pointed at a different file; replaced with one pointing at the current source. |
| `unchanged` | Existing symlink already points at the correct source; no-op. |
| `skipped-real-file` | A non-symlink file exists at the target path. The installer refuses to overwrite real files; the caller surfaces a warning so the user can clean up manually. |

The target dir is chosen to coexist with the user's pre-existing `~/.config/agent-shared/sync_mcp_configs.py` system, which independently distributes registration metadata from `~/.config/agent-shared/mcp_servers.json` to global Claude (`~/.claude.json`) and Codex (`~/.codex/config.toml`) configs. The playbook installer writes registration directly per-agent via the existing Tier 1 adapter MCP flows; `sync_mcp_configs.py` can additionally be re-run by the user to refresh global registrations from the shared source.

## Placeholder expansion

`server.json` in a bundle uses `{{AGENT_SHARED_MCP_DIR}}` as the install path so the file stays portable in the playbook repo (no machine-specific absolute paths). At install time, each Tier 1 adapter calls `_loader.expand_agent_shared_placeholder(config, name)` which replaces every occurrence with `str((Path.home() / ".config" / "agent-shared" / "mcp_servers" / name).resolve())`. The resolved JSON is then written into the per-agent MCP config.

Example `server.json`:
```json
{
  "command": "python3",
  "args": ["{{AGENT_SHARED_MCP_DIR}}/agent_memory_mcp.py"],
  "env": {
    "PYTHONPATH": "{{AGENT_SHARED_MCP_DIR}}"
  }
}
```

After expansion in `~/.codex/config.toml`:
```toml
[mcp_servers.agent-memory-bridge]
command = "python3"
args = ["/Users/rehan-8v/.config/agent-shared/mcp_servers/agent-memory-bridge/agent_memory_mcp.py"]

[mcp_servers.agent-memory-bridge.env]
PYTHONPATH = "/Users/rehan-8v/.config/agent-shared/mcp_servers/agent-memory-bridge"
```

## Authoring shape

To add a new locally-hosted MCP:
1. Create `mcp/<name>/` in the playbook.
2. Add `<name>.py` (and any supporting `.py` files).
3. Write `server.json` with `command`, `args`, optional `env`. Use `{{AGENT_SHARED_MCP_DIR}}` for paths the installer should resolve.
4. Write `README.md` covering: what the MCP does, the env vars it honors, a manual smoke-test command.
5. Run `make test`. The `test_materialize_mcp_sources` check confirms the symlink-creation flow works for the new bundle.
6. PR per `CONTRIBUTING.md`.

The bundle authoring guide lives in `mcp/README.md` ("Bundle dirs" section); this ADR records the architectural decision.

## Reject if

- A future bundle has dependencies the playbook cannot reasonably distribute (e.g. compiled extensions, custom system libraries, large model weights). At that point, the bundle should ship as a separate installable package (PyPI / Homebrew / etc.) and the playbook reverts to a flat `mcp/<name>.json` referencing the installed package.
- The two-layout coexistence proves confusing to authors in practice (frequent "do I write a flat file or a bundle" questions). If observed, harden `mcp/README.md` with a decision tree first; only collapse the two layouts if confusion persists across multiple PRs.

## Consequences

- `mcp/` gains one new subdirectory per locally-hosted MCP. Currently one (`agent-memory-bridge/`); expected to remain small (1 to 3 bundles) since most MCPs are published packages.
- `_loader.py` carries three new public symbols: `materialize_mcp_sources`, `expand_agent_shared_placeholder`, `AGENT_SHARED_MCP_DIR`. These are stable; adapter code calls them; tests cover them.
- `install.py` calls `materialize_mcp_sources` once before adapter dispatch so every adapter sees the symlinks already in place.
- The em-dash lint (`scripts/check_em_dashes.py`) scans `mcp/**/*.py` and `mcp/**/*.md` so bundled source plus per-server READMEs ship without em-dash drift. One file (`memory_curator.py`) is allowlisted because its `ENTRY_RE` regex character class legitimately needs the em-dash character to parse memory entries.
- `CONTEXT.md` glossary already updated to describe the two MCP shapes; the seven-bucket adapter-coverage table is correct as-is (MCP applies to Claude Code, Cursor, Codex, Windsurf; flat vs bundle is invisible to consumers).

## Source

- Internal: v0.2.1 harness import pass; Cursor review R2 flagged that the new format needed an ADR.
- ADR-0001 (skill format) for the precedent of versioned + frontmatter-bearing content.
- `~/.config/agent-shared/sync_mcp_configs.py` for the coexisting MCP distribution layer.
