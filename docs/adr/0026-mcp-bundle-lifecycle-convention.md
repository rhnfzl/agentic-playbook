# 0026. MCP bundle lifecycle: bundle = content provider, playbook = orchestrator

## Status

Accepted (2026-05-25); convention support landed in v0.4. anchored-fs decomposition queued as follow-up.

Partially superseded by ADR-0032 (v0.5: anchored-fs as first conforming heavy bundle). ADR-0032 takes a smaller-step path than the "Consequences for anchored-fs migration" section below; the deeper decomposition remains queued.

## Context

ADR-0012 established the two MCP layouts (flat `mcp/<name>.json` for hosted MCPs, bundle `mcp/<name>/{server.json, *.py}` for locally-hosted Python MCPs). Through v0.3, two kinds of bundles emerged with very different responsibility splits:

1. **Minimal bundle (`agent-memory-bridge`)**: source files + `server.json` + `README.md`. Relies entirely on the playbook's symlink + adapter MCP-registration flow. Total bundle code: zero install logic; just the MCP server source.
2. **Heavy bundle (`anchored-fs`)**: a 345-line self-installer (`mcp/anchored-fs/install.py`) that handles its own `~/.claude/settings.json` hook registration, `~/.claude.json` MCP registration, `~/.codex/config.toml` MCP registration, venv bootstrap, launchd plist install, health checks, status / uninstall lifecycle. Bundle-owned `hooks/` directory. Steps on the playbook's adapter MCP-registration flow.

The asymmetry caused two concrete failure modes:

- **Double registration**: anchored-fs's install.py writes MCP entries to claude.json; the playbook's claude_code adapter would write the same entries. Whichever ran second won. Order dependent.
- **Hook drift**: bundle-owned `mcp/anchored-fs/hooks/` was a separate location from root `hooks/`. Same pattern Candidate 3 just fixed for skill-local human-html hooks (root hooks/ canonicalized in ADR-0027 sibling work).

## Decision

Bundle is a content provider; the playbook orchestrates. Bundles own only what's genuinely bundle-unique (venv + health checks); registration moves to the playbook's standard Adapter pipeline.

### Minimal bundle layout

A new bundle SHOULD ship:

- `server.json` (**required**) - MCP registration the playbook reads via `_loader.load_mcp_configs`. The flat-vs-bundle layout from ADR-0012 is unchanged.
- `*.py` source (**required**) - what gets symlinked into `~/.config/agent-shared/mcp_servers/<name>/`.
- `bootstrap.sh` (**optional**) - idempotent setup (venv creation, dependency install, runtime state prep). The playbook installer runs this AFTER source symlink and BEFORE adapter MCP registration so adapters can shell out to a working server if needed.
- `health.sh` (**optional**) - exit 0 if healthy. Future `make doctor` aggregates these across detected bundles.
- `teardown.sh` (**optional**) - called on `make remove` before the playbook unlinks the bundle's symlinks. Most bundles do not need it.

### Ownership split

The playbook owns:

- MCP server registration in per-Adapter configs (`~/.claude.json`, `~/.codex/config.toml`, `~/.cursor/mcp.json`, etc.)
- Hook script registration in `~/.claude/settings.json` (via claude_code adapter)
- Source-file symlinking via `_loader.materialize_mcp_sources`

The bundle owns:

- `bootstrap.sh` (venv, dependencies, runtime state)
- `health.sh` (self-check)
- `teardown.sh` (cleanup beyond symlink removal)
- Bundle source code

### Bundle hooks live at root

Hooks that belong to a bundle conceptually (e.g. anchored-fs's PreToolUse enforcement) live at `hooks/<bundle-name>-*.sh` per ADR-0024 sibling Candidate 3 (root `hooks/` is canonical). The bundle does not maintain its own `hooks/` directory.

### bootstrap.sh lifecycle integration

`scripts/install.py` runs bootstrap.sh for each detected bundle after source symlinking, before adapter dispatch. 180s timeout per bundle. Errors print to stderr but never block the install. Bundles without bootstrap.sh are no-ops (convention: if the file exists, run it).

## Consequences

- New bundles automatically inherit the lifecycle convention. Any bundle that ships `bootstrap.sh` gets the playbook's invocation for free.
- `agent-memory-bridge` already fits the new shape (zero install code; just source + server.json).
- `anchored-fs` does NOT fit yet. Its 345-line `install.py` predates the convention and continues to self-register for now. A follow-up PR will decompose into `bootstrap.sh` (venv + launchd) + `health.sh` (daemon socket check), deleting the registration logic that the playbook now owns. The decomposition is queued; this ADR captures the destination.
- `mcp/README.md` documents the convention so contributors authoring new bundles have a clear template.

## Rejected alternatives

- **Bundle = mini-installer (status quo with cleaner contract).** Bundle keeps its own install.py with init/check/status/uninstall. Playbook delegates: "I'll do the symlink; you do the rest." Minimal change to anchored-fs. Rejected: every new heavy bundle would reimplement settings.json / claude.json registration, and the double-registration failure mode would persist.
- **Hybrid: bundle declares lifecycle steps in server.json; playbook calls them.** `server.json` would gain a `lifecycle` block with explicit script paths. Most ceremony; every new bundle must understand the lifecycle contract. Convention via well-known filenames is simpler.

## Consequences for anchored-fs migration

The follow-up PR will:

- Delete `mcp/anchored-fs/install.py`'s MCP registration code (`_register_claude_json`, `_register_codex_toml`).
- Delete its hook-registration code (the hook entries in `~/.claude/settings.json`).
- Move `mcp/anchored-fs/hooks/` contents to root `hooks/anchored-fs-*.sh` with `# PLAYBOOK-HOOK-EVENT:` headers per ADR-0027.
- Split the remaining venv + check + uninstall into `bootstrap.sh` + `health.sh` (+ optional `teardown.sh`).
- Net change: ~250 lines absorbed by playbook adapter pipeline, ~95 lines split between bootstrap.sh + health.sh.

## Related

- ADR-0012 (mcp/ bundle directory): the two layouts are unchanged; this ADR extends the bundle layout with the lifecycle convention.
- ADR-0018 (anchored-fs vendoring): the bundle stays vendored; only its install responsibility shape changes.
- ADR-0024 (Adapter Protocol): bundle MCP entries flow through the standard adapter pipeline.
- ADR-0027 (canonical Hook source): bundle hooks live at root `hooks/`.
- ADR-0032 (v0.5: anchored-fs as first conforming heavy bundle): the smaller-step path actually shipped in v0.5; partially supersedes "Consequences for anchored-fs migration" above.
- ADR-0037 (v0.8: generalized hook adapter scoping + anchored-fs hook migration): finishes the anchored-fs migration line item above. The Claude Code hooks moved to root `hooks/anchored-fs-{pretool-edit,posttool-read}.sh` and the bundle stopped touching `~/.claude/settings.json`. The `PLAYBOOK-HOOK-ADAPTERS: claude-code` header introduced for this migration generalizes the per-adapter scoping mechanism.
- Source: 2026-05-25 grilling session captured in `docs/human-html/2026-05-25-architecture-coding-agents-playbook-architecture-opportunities.html`.
