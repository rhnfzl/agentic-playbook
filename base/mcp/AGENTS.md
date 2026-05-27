# MCP Servers

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

MCP (Model Context Protocol) server registrations and bundled source. Per ADR-0012, each entry is either a flat `<name>.json` (registration only) or a directory `<name>/{server.json, *.py, README.md}` (source bundled, materialized at install).

## What Lives Here

- `<name>.json` flat registrations: atlassian, VCS, code-review-graph, error-tracking, slack, code-quality, tavily.
- `<name>/` directory bundles: `agent-memory-bridge/`, `anchored-fs/`.
- `README.md` describes the registration vs bundle contract.

## Local Commands

- The installer materializes registrations into the adapter MCP config (e.g. `~/.codex/config.toml`).
- For bundled MCPs, the installer also writes the source to `~/.config/agent-shared/mcp_servers/<name>/` and symlinks server.json there.

## Edit Rules

- Flat JSON registrations contain only the MCP entry shape; the installer expands `{{AGENT_SHARED_MCP_DIR}}` at materialize time.
- Bundle directories include LICENSE, server.json, source, README. Vendor decisions for anchored-fs live in ADR-0018.
- Adding a new MCP requires updating `mcp/README.md` and the inspirations doc when relevant.

## Required Checks

- JSON validity: `python3 -c 'import json, sys; json.load(open(sys.argv[1]))' mcp/<name>.json`.
- Bundle sanity: `mcp/<name>/server.json` exists and references files inside the same dir.
- License present for vendored bundles.

## Required Skills

- None mandatory. When adding a vendored bundle, follow the pattern in `mcp/agent-memory-bridge/`.

## Do Not

- Vendor MCP source without a LICENSE file. If the upstream has no LICENSE, catalog refer-only instead.
- Hardcode absolute paths. Use `{{AGENT_SHARED_MCP_DIR}}` placeholder.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding an MCP or updating bundle sources.
