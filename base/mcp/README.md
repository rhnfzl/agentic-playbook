# MCP server configs

This directory holds shareable Model Context Protocol (MCP) server configurations for the playbook. Each `.json` file is a single server definition that the installer materializes into whichever coding agent the user selected.

## What MCP is

MCP (Model Context Protocol) is the open standard that lets AI agents call external tools and data sources (Slack, web search, custom HTTP services, databases, issue trackers, etc.) without each tool being baked into the agent. One server config works across Claude Code, Cursor, Codex CLI, Windsurf, and any other MCP-compliant client. See modelcontextprotocol.io for the spec.

## Two MCP shapes coexist

The directory holds two distinct entry shapes; both are discovered by `_loader.load_mcp_configs`:

1. **Flat config** at `mcp/<name>.json` for hosted, npx, or uvx MCPs you do not host source for (Tavily, Slack, etc.). One JSON file = one server.
2. **Bundle dir** at `mcp/<name>/` containing `server.json` + `*.py` source + `README.md` for locally-hosted Python MCPs whose source you want shipped with the playbook (`agent-memory-bridge`). The installer:
   - Symlinks the `*.py` files into `~/.config/agent-shared/mcp_servers/<name>/` via `_loader.materialize_mcp_sources`.
   - Reads `server.json`, expands its `{{AGENT_SHARED_MCP_DIR}}` placeholder to the symlink target, then writes the resolved config into each enabled agent's MCP registry.

The symlink-from-playbook pattern coexists with the user's `~/.config/agent-shared/sync_mcp_configs.py` (which distributes registration metadata into global Claude/Codex configs). Editing the `.py` in the playbook repo updates the symlink target instantly; no re-install needed for code changes.

## What ships in this directory

### Flat configs (hosted / npx / uvx servers)

| File | What it connects to | Transport | Notes |
|---|---|---|---|
| `code-review-graph.json` | Local code-review-graph service | stdio (`uvx code-review-graph serve`) | Disabled by default; enable only when graph tools are needed |
| `slack.json` | Slack | stdio (npm `@modelcontextprotocol/server-slack`) | Workspace via SLACK_TEAM_ID |
| `tavily.json` | Tavily web search | Streamable HTTP | API key passed in URL query |

Each entry contains `{{REPLACE_WITH_*}}` placeholders. The installer copies the configs verbatim; you fill in real tokens AFTER installing, per the agent-specific instructions below. Servers marked `enabled: false` are intentionally shipped disabled to avoid startup warnings until a teammate opts into them.

Additional MCP server configurations (Atlassian, VCS host, error-tracking, code-quality, etc.) are designed in the upstream and intentionally not shipped in this public mirror. The list above reflects only what the downstream portfolio currently distributes.

### Bundle dirs (Python source distributed with the playbook)

| Bundle | What it does | Files | Notes |
|---|---|---|---|
| `agent-memory-bridge/` | SQLite-backed shared memory store + FastMCP wrapper + co-located CLI curator. Lets Claude Code, Codex, and Cursor read and write the same per-workspace memory pool. | `agent_memory_bridge.py`, `agent_memory_mcp.py`, `memory_curator.py`, `server.json`, `README.md` | Symlinked to `~/.config/agent-shared/mcp_servers/agent-memory-bridge/` on install. See `mcp/agent-memory-bridge/README.md` for env vars and manual test. |
| `anchored-fs/` | Globally-installed MCP filesystem server with `prefix[upto]suffix` anchored-edit support, fuzzy path resolution, stale-read detection. | `core/`, `daemon/`, `tools/`, `delegate.py`, `server.py`, `server.json`, `README.md`, `install.py` | Currently self-installs via its own `install.py` (run separately). A future PR will decompose into the standard `bootstrap.sh` / `health.sh` convention below; see ADR-0026. |

### Bundle lifecycle convention (ADR-0026)

New bundles SHOULD adopt this minimal shape so the playbook installer (not the bundle) owns registration:

- `server.json` (required) - MCP registration the playbook reads
- `*.py` source (required) - what gets symlinked into `~/.config/agent-shared/mcp_servers/<name>/`
- `bootstrap.sh` (optional) - idempotent setup (venv, dependencies, runtime state). The playbook installer runs this AFTER source symlink and BEFORE adapter MCP registration so adapters can shell out to a working server if needed. If absent, the bundle is treated as "no bootstrap required".
- `health.sh` (optional) - exit 0 if healthy. Future `make doctor` aggregates these.
- `teardown.sh` (optional) - called on `make remove` before the playbook unlinks the bundle's symlinks. Most bundles don't need it.

What the bundle MUST NOT own anymore (this is the playbook's job per ADR-0024):

- MCP server registration in per-Adapter configs (`~/.claude.json`, `~/.codex/config.toml`, etc.)
- Hook script registration in `~/.claude/settings.json`. Bundle hooks live at root `hooks/<bundle-name>-*.sh` per Candidate 3.

The `anchored-fs/install.py` predates this convention and continues to self-register for now; the decomposition into `bootstrap.sh` + `health.sh` is queued as a follow-up.

## Where each adapter installs these configs

| Coding agent | Config file written by `make install` | Format |
|---|---|---|
| Claude Code | `~/.claude.json` (mcpServers block) | JSON, the de-facto standard shape |
| Cursor | `~/.cursor/mcp.json` (user-level primary) and `<target>/.cursor/mcp.json` if `--target` passed | JSON, same shape as Claude |
| Codex CLI | `~/.codex/config.toml` under `[mcp_servers.<name>]` blocks | TOML (the adapter converts at install time) |
| Windsurf | `<target>/.windsurf/mcp.json` if `--target` passed | JSON, same shape as Claude |
| Pi | NOT installed (Pi has no native MCP support; see pi.dev) | n/a (use the `pi-mcp-adapter` extension manually if needed) |

The Tier 3 adapters (Goose, Junie, Zed, Amp, etc.) do not receive MCP configs from the installer; configure those manually per each tool's docs.

## Step-by-step setup per coding agent

### Claude Code

1. Run `make install` and select `claude-code` at the agent prompt.
2. Open `~/.claude.json` in your editor. Find the `mcpServers` block. The playbook wrote new server entries; preserve any existing entries (the adapter's MCP merge does not overwrite by name).
3. For each server you want to use, replace the `{{REPLACE_WITH_*}}` placeholders with real values:
   - Slack: Bot token (xoxb-...) + Team ID (Slack workspace settings)
   - Tavily: API key (tavily.com dashboard)
   - code-review-graph: workspace path, then set `enabled` to `true` only when you need graph-backed review tools
4. Restart Claude Code (`exit` then `claude` again).
5. Verify: run `/mcp` inside Claude Code. The new servers should appear with their tools listed.

CLI alternative (avoids hand-editing JSON):
```bash
claude mcp add tavily --url 'https://mcp.tavily.com/mcp/?tavilyApiKey=...'
claude mcp list  # verify
```

The `~/.claude.json` path is the authoritative one; `~/.claude/settings.json` does NOT load MCP servers (this trips up new users; confirmed Anthropic behavior).

### Cursor (IDE and CLI)

1. Run `make install` and select `cursor` at the agent prompt. Default install is USER-LEVEL (`~/.cursor/mcp.json`) so the configs follow you across every Cursor CLI project.
2. Open `~/.cursor/mcp.json` and replace placeholders with real values (same as Claude Code step 3 above).
3. Restart Cursor (or click Reload in `Settings > Tools & MCP`).
4. Verify: open `Settings > Tools & MCP`. New servers appear in the list with green check marks when initialized.

If you have project-specific servers, add them to `.cursor/mcp.json` in the project root (you must explicitly approve project-level servers in `Settings > MCP` for security).

Cursor caveats:
- 40-tool limit across all enabled servers (Cursor warns and silently drops tools above the limit; disable individual tools if you go over).
- Project-level configs require manual approval; user-level configs do not.
- Remote SSE transport has a known fallback bug (March 2026 forum); if a server fails with HTTP 404 on POST, wrap it in `mcp-remote` as a stdio proxy at the config layer.

### Codex CLI

1. Run `make install` and select `codex` at the agent prompt. The adapter materializes MCP configs as TOML blocks in `~/.codex/config.toml` under `[mcp_servers.<name>]` headings.
2. Open `~/.codex/config.toml`. Find the managed block (between `# coding-agents-playbook BEGIN/END` markers). For each `[mcp_servers.<name>]` block, replace placeholders with real values.
3. Restart Codex (`exit` then `codex` again).
4. Verify: run `/mcp` inside Codex CLI. Servers appear with their tools.

CLI alternative:
```bash
codex mcp add tavily --url 'https://mcp.tavily.com/mcp/?tavilyApiKey=...'
```

Optional Codex settings you can add per server (see developers.openai.com/codex/config-reference):
- `enabled = false` to disable without removing
- `startup_timeout_sec = 30` to allow longer startup (default 10s; raise for slow Docker-stdio servers if any are added locally)
- `tool_timeout_sec = 120` for slow tools
- `required = true` to fail Codex startup if the server cannot initialize

### Windsurf

1. Run `make install --target /path/to/project` and select `windsurf`. The adapter writes `<target>/.windsurf/mcp.json`. User-level Windsurf MCP lives at `~/.codeium/windsurf/mcp_config.json` and is NOT automatically populated (manage it via the Windsurf MCP plugin store or hand-edit).
2. Open the project's `.windsurf/mcp.json` and replace placeholders with real values.
3. Restart Windsurf or click the refresh button in Cascade settings under "Plugins (MCP servers)."
4. Verify: open Cascade settings, scroll to MCP servers, confirm the new entries show green connection indicators.

Windsurf has a 100-tool ceiling across all servers (higher than Cursor's 40). Use the per-tool toggle in Cascade settings if you approach it.

### Pi

Pi (pi.dev) explicitly omits native MCP support per its design philosophy. If you want MCP in Pi, install the third-party `pi-mcp-adapter` extension:

```bash
pi install npm:pi-mcp-adapter
```

The adapter exposes MCP servers through a proxy tool that avoids the context bloat of full per-server tool registration. Configure servers in `~/.pi/agent/settings.json` or import an existing Claude / Cursor mcp.json via the adapter's `import` command.

This playbook's installer does NOT auto-install pi-mcp-adapter (tracked in `docs/research/upcoming-adapters.md`).

## How to add a new MCP server to the playbook

1. Decide what the server connects to and how it's transported (stdio / SSE / Streamable HTTP).
2. Create `mcp/<name>.json` following the standard JSON shape:
   ```json
   {
     "command": "npx",
     "args": ["-y", "package-name"],
     "env": {
       "API_KEY": "{{REPLACE_WITH_YOUR_API_KEY}}"
     }
   }
   ```
   Or for remote HTTP:
   ```json
   {
     "type": "http",
     "url": "https://example.com/mcp",
     "headers": { "Authorization": "Bearer {{REPLACE_WITH_TOKEN}}" }
   }
   ```
3. Use `{{REPLACE_WITH_*}}` for every secret or user-specific value. Never commit real tokens.
4. Run `make install --target /tmp/test` to verify the adapters can materialize the new config without errors.
5. PR per `CONTRIBUTING.md` (one reviewer approval, owner field maintained).

The installer treats `mcp/*.json` files as the source of truth. Adding a new file = adding a new server to every adapter's MCP block. Removing a file removes it from future installs but does NOT remove already-installed entries (those are preserved on purpose).

## Where secrets should live

NEVER commit real tokens to `mcp/*.json`. Patterns the playbook supports:

- **Inline placeholders** (`{{REPLACE_WITH_*}}`): user edits the installed file after install. Simplest; tokens live in each agent's own config file (`~/.claude.json`, `~/.cursor/mcp.json`, etc.).
- **Env var references** (Claude Code only): use `${TOKEN_NAME}` or `${TOKEN_NAME:-default}` syntax in `.mcp.json` per Anthropic's docs. Tokens live in your shell environment.
- **Bearer token env var ref** (Codex only): `bearer_token_env_var = "GITHUB_PAT"` in the TOML block. Codex reads the env var at call time.

The playbook ships with placeholders (option 1) as the default. If your security policy forbids per-agent config files containing tokens, switch to options 2 or 3 in your local install.

## References

- [modelcontextprotocol.io](https://modelcontextprotocol.io) (spec)
- [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp) (Claude Code MCP docs)
- [docs.cursor.com/context/mcp](https://docs.cursor.com/context/mcp) (Cursor MCP docs)
- [developers.openai.com/codex/config-reference](https://developers.openai.com/codex/config-reference) (Codex `mcp_servers` table reference)
- [windsurf.com/university/general-education/intro-to-mcp](https://windsurf.com/university/general-education/intro-to-mcp) (Windsurf MCP intro)
- [pi.dev/packages/pi-mcp-adapter](https://pi.dev/packages/pi-mcp-adapter) (Pi extension for optional MCP support)
