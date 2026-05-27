# anchored-fs

> **Playbook bundle (v0.3, ADR-0018):** This directory is the canonical upstream for anchored-fs. Run `make install` from the playbook root to symlink it to `~/.config/agent-shared/mcp_servers/anchored-fs/`. If you already have a real (non-symlink) anchored-fs install at that path, back it up first: `mv ~/.config/agent-shared/mcp_servers/anchored-fs ~/.config/agent-shared/mcp_servers/anchored-fs.bak` then re-run `make install`. After symlink, the original `uv sync` + `uv run python install.py init` flow below still works; it just runs against the playbook copy.

Globally-installed MCP filesystem server with `prefix[upto]suffix` anchored-edit support, fuzzy path resolution, stale-read detection, and auto-graduation policies. Works for Claude Code (via PreToolUse + PostToolUse hooks), Codex (via filesystem MCP), and any MCP-speaking client.

## What it does

Inspired by antirez's DwarfStar `[upto]` trick (2026-05-24). Replaces verbose `old_text=<huge block>` edits with `prefix[upto]suffix` anchors that resolve to a unique file span server-side. Plus three other validators: anchor-failure rescue payloads, fuzzy path resolution on Read failure, and stale-read detection via content hashing.

## Install (playbook-managed; preferred)

`make install` from the playbook root is the canonical install path. The playbook now owns BOTH MCP registration AND Claude Code hook registration for anchored-fs as of ADR-0037 (v0.8):

```bash
cd /path/to/coding-agents-playbook
make install
```

What the playbook does:

- Symlinks `mcp/anchored-fs/` into `~/.config/agent-shared/mcp_servers/anchored-fs/`.
- Writes the `anchored-fs` MCP entry into each detected agent's MCP config (`~/.claude.json`, `~/.codex/config.toml`, `~/.cursor/mcp.json`, `<target>/.windsurf/mcp.json`).
- Copies the shell wrappers `hooks/anchored-fs-pretool-edit.sh` + `hooks/anchored-fs-posttool-read.sh` into `~/.claude/hooks/` (the wrappers declare `PLAYBOOK-HOOK-ADAPTERS: claude-code` so only the claude-code adapter installs them). The wrappers exec the Python implementations at `~/.config/agent-shared/mcp_servers/anchored-fs/hooks/claude-code/*.py`.
- Registers the wrapper paths in `~/.claude/settings.json` under PreToolUse + PostToolUse, alongside every other playbook hook.

Then run the bundle bootstrap (still owned by anchored-fs because it sets up the launchd plist + state dirs):

```bash
cd ~/.config/agent-shared/mcp_servers/anchored-fs
uv sync
uv run python install.py init   # forwards to bundle/install.py
```

This step now does NOT touch `~/.claude/settings.json` (per ADR-0037); the playbook owns that. It still:

- Writes `manifest.json` describing the installed shape (schema_version pinned).
- Installs the launchd LaunchAgent (`~/Library/LaunchAgents/com.anchored-fs.daemon.plist`) for the daemon.
- Creates state directories at `~/.config/agent-shared/state/` and `~/.config/agent-shared/run/`.

After install, the daemon auto-starts (KeepAlive=true, RunAtLoad=true) and restarts on crash.

### Upgrading from v0.7

If you installed anchored-fs before ADR-0037 (v0.7 or earlier), `~/.claude/settings.json` may contain hook entries pointing directly at `mcp/anchored-fs/hooks/claude-code/*.py`. After running `make install` on v0.8+, the playbook adds the wrapper entries alongside but does not remove the legacy direct-Python entries (the playbook only owns what it wrote itself, per ADR-0023). Both work; the legacy entries are redundant. To clean up, manually remove any PreToolUse/PostToolUse `command` entries in `~/.claude/settings.json` that match `*mcp/anchored-fs/hooks/claude-code/*.py` and keep the wrapper entries pointing at `~/.claude/hooks/anchored-fs-*.sh`.

## Install (standalone; no playbook)

```bash
cd ~/.config/agent-shared/mcp_servers/anchored-fs
uv sync
uv run python install.py init
```

The bundle install handles only the bundle-internal pieces: state directories at `~/.config/agent-shared/state/` and `~/.config/agent-shared/run/`, the launchd LaunchAgent (`~/Library/LaunchAgents/com.anchored-fs.daemon.plist`), and the rendered `manifest.json`. Per ADR-0026 + ADR-0037, the bundle does NOT write `~/.claude.json`, `~/.codex/config.toml`, or `~/.claude/settings.json` in either install mode. Standalone installs therefore leave you with a working daemon but NO agent-discoverable MCP entry and NO Claude Code hook surface. To make the daemon visible to an agent in standalone mode, either:

1. Run the playbook-managed flow above (preferred), or
2. Hand-add an MCP entry pointing at `~/.config/agent-shared/mcp_servers/anchored-fs/.venv/bin/python -m server --allowed-dir <path>` into your agent's MCP config, and hand-register the hooks under `hooks/claude-code/*.py` in `~/.claude/settings.json`.

## Verify

```bash
uv run python install.py check    # exits 0 if wiring intact
uv run python install.py status   # shows current modes + adoption rate
```

## Uninstall

```bash
uv run python install.py uninstall
```

State files at `~/.config/agent-shared/state/` are preserved (not removed) so re-install picks up your prior history.

## How it works

- **Subprocess proxy:** Our FastMCP server wraps the stock `@modelcontextprotocol/server-filesystem@2026.1.14` via stdio JSON-RPC. We override `edit_file` with `[upto]` support and add `preview_edit_match`. Everything else (read, write, list, search, etc.) passes through transparently.
- **Daemon:** A launchd-supervised Unix-socket server loads `core/` once and serves hook calls in ~5 ms (vs 80-150 ms Python cold start). Hook scripts (`pretool_edit.py`, `posttool_read.py`) are thin socket clients.
- **Auto-graduation:** Telemetry-driven policy engine flips `edit_anchor` mode from `auto_rescue` → `force_reject` when voluntary `[upto]` adoption stays below 30% after 4 weeks. Flips `stale_read_guard` from `warn` → `block` when warn-quality stays high.

## Files

- `core/` — pure logic (upto_resolver, envelope, state_store, manifest, allowed_root, path_resolver, stale_read, adoption_tracker, graduation)
- `tools/` — edit_file + preview_edit_match (FastMCP @tool wrappers)
- `delegate.py` — subprocess proxy to stock filesystem MCP
- `server.py` — FastMCP entrypoint
- `daemon/` — Unix socket server + thin client + launchd plist
- `hooks/claude-code/`: PreToolUse + PostToolUse hook implementations (Python). Invoked by the playbook wrappers at `<playbook>/hooks/anchored-fs-*.sh` per ADR-0037 (v0.8).
- `install.py`: backwards-compat shim forwarding to `bundle/install.py`. Preserves the documented `uv run python install.py <subcommand>` entry point.
- `bundle/install.py`: canonical `init` / `repair` / `check` / `uninstall` / `status` implementation (manifest-driven). Per ADR-0026 + ADR-0037, this no longer mutates `~/.claude/settings.json` or `~/.claude.json`; the playbook adapter pipeline owns those.
- `bundle/bootstrap.sh`: convention-conformant bootstrap entry, today a no-op since registration moved to the playbook (per ADR-0026 v0.5 extension).
- `bundle/health.sh`: convention-conformant health check, aggregated by `make doctor` (v0.8 B1).
- `templates/manifest.json`: installation template.

## Design spec

See the architecture spec at `docs/human-html/2026-05-24-architecture-anchored-filesystem-framework-global-edit-anchor-path-resolver-stale-read-mcp.html` in the upstream workspace (`/Users/rehan-8v/team/team_LLM_Systems`).

## Hook ownership (ADR-0035 / ADR-0036 / ADR-0037)

ADR-0037 (v0.8) finished the anchored-fs hook migration. The Claude Code hooks now have the same ownership model as every other playbook hook: shell wrappers at root `hooks/anchored-fs-*.sh` are the canonical registration surface; the Python implementations under `mcp/anchored-fs/hooks/claude-code/` are bundle-internal.

| | All playbook hooks (including anchored-fs since v0.8) |
|---|---|
| Canonical source | `hooks/<name>.sh` or `skills/<cat>/<skill>/hooks/<name>.sh` |
| Materialization | `~/.claude/hooks/`, `~/.codex/hooks/`, etc. (per claude-code adapter) |
| Runtime registration | playbook adapter writes the entry into the agent's native config |
| Verification | `make doctor-verify` (`make doctor` aggregates `bundle/health.sh` exit codes) |
| Scoping | `PLAYBOOK-HOOK-ADAPTERS: claude-code` restricts to Claude Code (the only adapter whose hook payload format the Python implementations parse) |

`anchored-fs install.py init` no longer mutates `~/.claude/settings.json`; the playbook owns that. `init` still creates the state directories, writes `manifest.json`, and installs the launchd LaunchAgent. The bundle's `check` command now verifies that the playbook wrapper at `~/.claude/hooks/anchored-fs-pretool-edit.sh` is present (presence is the playbook's layer-2 ownership signal; `make doctor-verify` plus a fresh Claude session covers layer-3).

Files retained inside the bundle for context:

- `hooks/claude-code/pretool_edit.py` — PreToolUse implementation invoked by the shell wrapper.
- `hooks/claude-code/posttool_read.py` — PostToolUse implementation invoked by the shell wrapper.

Files added to the playbook root in v0.8:

- `hooks/anchored-fs-pretool-edit.sh` — wrapper, declares `EVENT: PreToolUse` + `MATCHER: Edit|MultiEdit|Write` + `ADAPTERS: claude-code`.
- `hooks/anchored-fs-posttool-read.sh` — wrapper, declares `EVENT: PostToolUse` + `MATCHER: Read` + `ADAPTERS: claude-code`.

The wrappers resolve the Python implementations via `${ANCHORED_FS_ROOT:-${HOME}/.config/agent-shared/mcp_servers/anchored-fs}/hooks/claude-code/*.py`, so the standard playbook materialization path "just works" without per-machine env tweaks.

## Codex findings

See `CODEX_FINDINGS.md` for the running tracker of Codex review findings across tasks (apply during polish after Phase 0 GATE passes).
