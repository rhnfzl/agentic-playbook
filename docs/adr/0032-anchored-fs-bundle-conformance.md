# 0032. anchored-fs bundle conformance via wrapper layer (supersedes parts of ADR-0026)

## Status

Accepted (2026-05-25); landed in v0.5. Partially supersedes ADR-0026 "Consequences for anchored-fs migration".

## Context

ADR-0026 (MCP bundle lifecycle convention) established the `bundle/bootstrap.sh + bundle/health.sh` entry-point contract for heavy MCP bundles. Its "Consequences for anchored-fs migration" section planned the deep decomposition: delete `_register_claude_json`, delete `_register_codex_toml`, move bundle hooks into root `hooks/`, split the remaining venv + check + uninstall into bash, drop ~250 lines from the Python installer and reabsorb them into the playbook adapter pipeline.

That plan is sound long-term but expensive in one step:

- `mcp/anchored-fs/install.py` is 345 lines of state-machine code: manifest writes, settings.json hook registration, claude.json MCP registration, codex config.toml MCP registration, launchd plist install, venv bootstrap, uninstall, status. Replacing each piece with shell loses the type safety and the manifest abstraction that make the bundle maintainable.
- The deletions land safely only once the claude_code adapter owns hook registration end to end (ADR-0029) AND the per-tool adapters (Cursor/Codex etc.) handle their own MCP registration symmetrically. Both happen in v0.5 but the deletions themselves need a follow-up cleanup PR to avoid coupling two large changes.

v0.5 needed anchored-fs to conform to the convention *as much as possible* without paying the rewrite cost yet, because the playbook installer's bundle dispatcher (`scripts/install.py _run_bundle_bootstraps`) probes `bundle/bootstrap.sh` and silently skips heavy bundles that ship a flat `install.py` instead.

## Decision

A smaller-step path that achieves convention conformance without rewriting install.py:

- `mcp/anchored-fs/install.py` moves into `mcp/anchored-fs/bundle/install.py`. Its `ANCHORED_FS_ROOT` constant changes from `Path(__file__).parent` to `Path(__file__).parent.parent` so existing template / manifest / plist paths keep resolving from the framework root one level up.
- `mcp/anchored-fs/bundle/bootstrap.sh` is a 5-line shell wrapper that calls `python3 install.py init` (the documented init subcommand; `install` was the wrong name in an interim commit and is fixed).
- `mcp/anchored-fs/bundle/health.sh` is a 5-line shell wrapper that calls `python3 install.py check`.
- `mcp/anchored-fs/install.py` becomes a 3-line `os.execv` shim into `bundle/install.py` so existing tests (`mcp/anchored-fs/tests/`) and README examples that invoke `python install.py <subcommand>` from the framework root keep working.
- `scripts/install.py _run_bundle_bootstraps` now probes `bundle/bootstrap.sh` first and falls back to the legacy flat location, so both v0.5+ heavy bundles and any minimal bundles authored against the original ADR-0026 wording stay supported.
- `core/`, `daemon/`, `hooks/`, `spike/`, `templates/`, `tests/`, `tools/` stay at the framework root unchanged.

The deletions ADR-0026 originally planned (`_register_claude_json`, `_register_codex_toml`, hook entry registration in install.py, bundle-owned `hooks/` directory) remain queued. They become safer to land once:

1. Every Tier 1 adapter (Claude, Codex, Cursor, Windsurf) handles its own MCP + hook registration. Done for Claude / Cursor / Codex / Cline / Copilot in v0.5; Windsurf hook registration deferred to v0.6.
2. The bundle-owned `hooks/` directory in `mcp/anchored-fs/hooks/` is migrated to root `hooks/anchored-fs-*.sh` with PLAYBOOK headers (ADR-0027).

When both prerequisites are met, a separate cleanup ADR (forthcoming, likely 0035 or later) will document the deep decomposition and let install.py shrink.

## Consequences

### Good

- anchored-fs now conforms to the convention from the playbook installer's perspective: `bundle/bootstrap.sh` is the canonical entry point, just like every future heavy bundle.
- Existing in-bundle tests + README examples keep working via the root shim.
- The convention is verifiable: a future check can fail-loud if a heavy bundle ships an install.py without a `bundle/bootstrap.sh` sibling.

### Bad

- Two-place entry point (root shim + bundle/install.py) is more files than strictly necessary. Eliminated once external callers migrate to bundle/install.py directly.
- The original ADR-0026 promise of "delete ~250 lines from install.py" is unfulfilled in v0.5. Tracked as future work; not regressed.
- The bundle's own `hooks/` directory still exists at `mcp/anchored-fs/hooks/` because the home claude_code adapter has not yet absorbed those hooks into root `hooks/`. ~~v0.6 candidate~~ Resolved in v0.8 via ADR-0037: shell wrappers at root `hooks/anchored-fs-*.sh` invoke the Python implementations; see the v0.8 amendment below.

## v0.8 amendment

ADR-0037 shipped the anchored-fs hook migration line item. The Python hooks under `mcp/anchored-fs/hooks/claude-code/` are now invoked via two new shell wrappers at root `hooks/anchored-fs-pretool-edit.sh` and `hooks/anchored-fs-posttool-read.sh`. The wrappers carry `PLAYBOOK-HOOK-EVENT`, `PLAYBOOK-HOOK-MATCHER`, and (new) `PLAYBOOK-HOOK-ADAPTERS: claude-code` headers, so the playbook's claude-code adapter installs them like every other hook and `make doctor-verify` covers them. `mcp/anchored-fs/bundle/install.py` no longer mutates `~/.claude/settings.json`: the `_add_hook` / `_remove_owned_hooks` / `_load_settings` / `_write_json` / `_backup` helpers were removed.

## Related

- ADR-0026 (MCP bundle lifecycle convention): the parent convention; this ADR refines its anchored-fs migration plan.
- ADR-0029 (hook reconciliation + matcher header): the prerequisite for fully removing anchored-fs's hook registration code.
- ADR-0037 (v0.8 generalized hook adapter scoping): completes the anchored-fs hook migration this ADR scoped.
- Source: Codex review of the v0.5 branch flagged the missing `bundle/bootstrap.sh` lookup; this ADR captures the smaller-step path that fix implies.
