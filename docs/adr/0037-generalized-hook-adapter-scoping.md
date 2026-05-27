---
status: accepted
date: 2026-05-25
supersedes: []
amends: ["0026", "0032"]
related: ["0034", "0035", "0036"]
---

# ADR-0037: Generalized hook adapter scoping + anchored-fs hook migration

## Status

Accepted. Implemented in v0.8.

## Context

ADR-0034 introduced the cross-agent hook contract: every hook script in
`hooks/` (or skill-owned `skills/<cat>/<name>/hooks/`) declares its own
event + matcher metadata, and the playbook adapter pipeline materializes
the script into each detected agent's native config (Claude Code, Codex,
Cursor, Cline, Copilot, Windsurf).

The contract already supported one form of per-adapter scoping:
`PLAYBOOK-HOOK-CURSOR-ONLY: true` flagged Cursor-only wrappers so the
other five hook adapters skipped them. The flag was Cursor-specific and
did not generalize.

Two pressures converged on the need for a broader mechanism:

1. **anchored-fs hooks are coupled to one adapter's payload.** Through
   v0.7, `mcp/anchored-fs/hooks/claude-code/{pretool_edit,posttool_read}.py`
   parsed Claude Code's `tool_input` + `tool_response` JSON. They had to
   ship for Claude Code and only for Claude Code. The bundle self-
   registered them by mutating `~/.claude/settings.json` from
   `bundle/install.py init`. That bypassed the playbook adapter pipeline,
   producing two parallel hook systems on one machine: shell-in-root hooks
   for everything else, Python-in-bundle for anchored-fs. The
   `hook_source_unification` gate (ADR-0035) and `doctor-verify`
   (ADR-0036) couldn't see the Python branch.
2. **Architecture review identified the duality as a v0.8 blocker.**
   The May 2026 architecture HTML doc resolved Candidate 6 (MCP bundle
   lifecycle seam) by saying bundles should be "content providers" and
   the playbook should own all registration. ADR-0026 + ADR-0032
   captured that direction but left the anchored-fs Claude Code hooks
   inside the bundle because the shell wrapper model didn't yet exist.

## Decision

**Add a generalized `PLAYBOOK-HOOK-ADAPTERS` header** parsed by
`scripts/hook_registration.py:resolve_hook_adapters`. The header value is
a comma-separated list of adapter slugs (`claude-code`, `codex`,
`cursor`, `cline`, `copilot`, `windsurf`). When present, only the listed
adapters install and register the hook. When absent, every hook-capable
adapter installs it (subject to the legacy `CURSOR-ONLY` filter).

`scripts/hook_registration.py:is_hook_for_adapter(hook, adapter_name)`
encapsulates the combined check (`CURSOR-ONLY` plus `ADAPTERS`
allowlist). Every adapter and `install.py:_hook_command_keys` /
`install.py:_windsurf_hook_names` call it so plan-time keyspace matches
write-time exactly. The target materializer's Cursor projection
(`scripts/target_materializer.py:_generate_cursor_hooks_json`) honors
the same filter.

**Migrate the anchored-fs Claude Code hooks to playbook ownership.**
Two new wrappers ship under `hooks/`:

- `hooks/anchored-fs-pretool-edit.sh` (`PLAYBOOK-HOOK-EVENT: PreToolUse`,
  `MATCHER: Edit|MultiEdit|Write`, `ADAPTERS: claude-code`)
- `hooks/anchored-fs-posttool-read.sh` (`EVENT: PostToolUse`,
  `MATCHER: Read`, `ADAPTERS: claude-code`)

Each wrapper resolves the Python implementation at
`~/.config/agent-shared/mcp_servers/anchored-fs/hooks/claude-code/*.py`
(the standard playbook materialization path produced by
`materialize_mcp_sources`) and execs it with `PYTHONPATH` pointing at
the bundle root so the daemon imports still resolve.

**Remove the bundle's hook self-registration.**
`mcp/anchored-fs/bundle/install.py` no longer mutates
`~/.claude/settings.json`. The helpers `_add_hook`,
`_remove_owned_hooks`, `_load_settings`, `_write_json`, and `_backup`
were removed to prevent silent re-introduction of the parallel system.
The bundle's `init` still creates `~/.config/agent-shared/state/`, the
launchd plist, and the default `anchored-fs.toml`; the bundle's `check`
now verifies the playbook-installed wrapper at
`~/.claude/hooks/anchored-fs-pretool-edit.sh` is present. The manifest
template retains its `hooks` block for documentation but it is no
longer consumed for write.

## Consequences

Positive:

- One canonical hook system. The hook_source_unification gate and
  doctor-verify cover anchored-fs hooks just like every other hook.
- Migration unblocks future bundles. Any future MCP bundle that needs
  Claude-Code-specific hooks ships a wrapper under root `hooks/` with
  `PLAYBOOK-HOOK-ADAPTERS: claude-code` instead of inventing a parallel
  installer.
- The header generalizes beyond anchored-fs. A future
  `windsurf-only-graph-update.sh` hook is one line away.

Negative:

- The wrapper layer is one extra hop. An Edit event flows: Claude Code →
  shell wrapper → Python implementation. The shell exec adds about 5 ms
  per fire; trivial against the hook's own daemon-socket round-trip.
- The Python implementation now sits behind a known-location path
  (`~/.config/agent-shared/mcp_servers/anchored-fs/`). If the user moves
  the playbook repo, `make install` must re-run; the wrapper's
  `ANCHORED_FS_ROOT` env-var override exists for advanced operators who
  want a non-standard layout.

Risk that may surface later:

- Users with a v0.7 install have `~/.claude/settings.json` entries
  registered by the bundle pointing at the Python file directly. When
  they run `make install` on v0.8+, the playbook adapter pipeline
  registers the wrapper alongside the existing Python-direct entry. The
  reconcile logic (`reconcile_claude_shaped_hooks_in_json`) only removes
  entries the playbook itself wrote in a prior run; v0.7's bundle-written
  entries pass through as "user-authored" and survive. Users see both:
  the wrapper (working) and the stale direct-Python entry (still
  working, but redundant). A v0.8 migration sweep in
  `bundle/install.py init` could clean those up, but doing so would
  require the bundle to know which entries it wrote in v0.7 (it doesn't
  record that). The lower-risk approach is to document the cleanup in
  the v0.8 release notes and `mcp/anchored-fs/README.md`: "if you
  upgraded from v0.7, run `make install` then optionally remove any
  `command` entry in settings.json that points directly at
  `mcp/anchored-fs/hooks/claude-code/*.py`." A regression test against
  a v0.7-baseline `settings.json` confirms the wrapper still registers
  cleanly when the legacy entries are present.

## Implementation

- `scripts/hook_registration.py`: `_HOOK_ADAPTERS_HEADER_RE`,
  `_HOOK_CAPABLE_ADAPTERS`, `resolve_hook_adapters()`,
  `is_hook_for_adapter()`.
- `scripts/install.py`: `_hook_command_keys` and `_windsurf_hook_names`
  call `is_hook_for_adapter()` so the lockfile's `managed_keys.hooks`
  per adapter matches what each adapter actually writes.
- `scripts/adapters/{claude_code,codex,cline,copilot,cursor,windsurf}.py`:
  each replaced the `is_cursor_only` filter with
  `is_hook_for_adapter(h, self.name)` (or `"cursor"` in the cursor
  target_materializer free function).
- `scripts/target_materializer.py:_generate_cursor_hooks_json`: filters
  by `is_hook_for_adapter(h, "cursor")` before generating the per-target
  Cursor projection.
- `hooks/anchored-fs-pretool-edit.sh` + `hooks/anchored-fs-posttool-read.sh`:
  new shell wrappers with the three required headers.
- `mcp/anchored-fs/bundle/install.py`: removed `_add_hook`,
  `_remove_owned_hooks`, `_load_settings`, `_write_json`, `_backup`;
  `init` no longer touches settings.json; `check` verifies the playbook
  wrapper at `~/.claude/hooks/anchored-fs-pretool-edit.sh`.
- `mcp/anchored-fs/tests/integration/test_install.py`: rewrites covering
  the v0.8 contract (init does not mutate settings.json; check requires
  playbook wrapper; uninstall preserves settings.json).
- `scripts/test_adapters.py:test_hook_coverage_per_adapter`: updated
  expected hook counts (11 total; claude-code = 10; others = 8).
- `tests/lifecycle/test_lifecycle.py`: new regression scenario covering
  anchored-fs wrapper install via the claude-code adapter and exclusion
  from cursor / windsurf / codex.

## Related

- ADR-0026 (MCP bundle lifecycle convention): bundle's role narrows
  further; hooks join MCP registration as playbook-owned.
- ADR-0032 (anchored-fs bundle conformance): ADR-0037 finishes the
  migration ADR-0032 scoped.
- ADR-0034 (cross-agent hook contract): the new header extends the
  contract; semantics still match the existing event/matcher headers.
- ADR-0035 (canonical hook source): the anchored-fs wrappers sit under
  canonical `hooks/`, not the bundle, in keeping with the unification
  rule for non-skill-owned hooks.
- ADR-0036 (three-layer content contract): the wrappers are layer-1
  artifacts and inherit the full layer-2/3 verification chain.
