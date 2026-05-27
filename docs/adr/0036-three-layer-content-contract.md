# ADR-0036: Three-layer content contract (canonical / materialization / runtime)

> **ADR = Architecture Decision Record.** A short document capturing one architectural decision plus the context that made it necessary and the consequences. See `docs/adr/README.md` for the full convention.

## Status

Accepted (2026-05-25); landed in v0.7.

## Context

Until v0.6, the playbook installer's success signal was "files exist where the lockfile says they should." That gives layer-1 (the author's canonical source) and layer-2 (what the installer wrote) but leaves layer-3 (what the agent runtime actually loads) verified only by hand. The Cursor install-surface lesson made the gap explicit:

- The `cursor-team-kit` plugin was filesystem-copied to `~/.cursor/plugins/local/` and the lockfile recorded a successful install. The plugin still failed to load because Cursor's agent session resolves plugins through the marketplace loader, not by walking `~/.cursor/plugins/local/`. Layer-2 looked done; layer-3 was empty.
- A separate v0.6 hook-parity diff introduced new Cursor `hooks.json` entries via `TargetMaterializer`. Lockfile said hooks registered; `cat ~/.cursor/hooks.json` was indeed populated. Only manual smoke-testing caught a case where the entries pointed at the right paths but Codex auto-promote logic was off, so the hooks fired under the wrong event. Lockfile + native config both said "done"; runtime behavior said otherwise.

The fix is not more hand-testing. The fix is to require every content type to document and verify all three layers, and to bake the discipline into checks, lifecycle tests, and the `playbook-doctor` UX.

## Decision

For every content type the playbook ships (skill, rule, hook, MCP server, agent definition, command, prompt, AGENTS.md fragment), the design and the documentation must spell out three paths:

1. **Canonical source** -- where the author edits. Single point of truth. Lives in `skills/<cat>/<name>/`, `rules/`, `hooks/`, `mcp/<name>/`, `commands/`, etc.
2. **Materialization** -- what the installer writes. The `~/.claude/skills/`, `~/.codex/skills/`, `~/.cursor/skills/`, `~/.cursor/hooks/`, project `.cursor/hooks/`, etc. paths. Captured in the lockfile.
3. **Runtime discovery** -- what the agent runtime actually loads. For hooks: the entry in `~/.cursor/hooks.json` (or equivalent native config) pointing at the materialized script. For skills: the agent's skill-loader path plus, where applicable, a new chat session. For MCP servers: the entry in the agent's MCP config plus a running server process.

A change is not "done" until all three layers are verified. Layer-1 and layer-2 alone are necessary but not sufficient. The playbook backs this rule with three machine-checkable rails:

- **Layer-1 integrity** -- `make check` includes `hook-source-unification` (ADR-0035) so two canonical sources cannot coexist for the same hook. Equivalent layer-1 gates exist for skill names, MCP bundles, and AGENTS.md fragments through other checks.
- **Layer-3 verification (test)** -- the lifecycle suite installs each adapter into a temp `$HOME` and parses the native config files. The test asserts: hook count per adapter, registered event names, script paths exist on disk. If `TargetMaterializer` writes a Cursor hooks.json but the entries are mis-shaped, the test fails.
- **Layer-3 verification (runtime UX)** -- `make doctor-verify` (alias `python3 scripts/install.py --verify`) reports a pass/fail map per detected Tier-1/2 adapter: lockfile entry count vs native config entry count vs on-disk script existence. A teammate runs this after `make install` and sees the same answer the lifecycle test would give.

## Consequences

### Good

- A new contributor (or a new content type) inherits the three-layer rule by template. Author the content, materialize it, document the native config or loader it ends up in. Three layers, three rails.
- "Is it really installed?" stops being a tribal-knowledge question. `make doctor-verify` returns a structured answer.
- The lifecycle suite catches install-surface regressions before merge. v0.6 hand-found two; v0.7 promotes the check to CI.

### Risks / open threads

- The `--verify` mode adds runtime cost to a fast command. Mitigation: the verify pass is opt-in (`--verify` flag, `make doctor-verify` target); the default `make doctor` stays detection-only and fast.
- Cursor's plugin marketplace flow still bypasses the playbook (`/add-plugin <repo>` is Cursor-native). The contract documents this explicitly so contributors don't reach for `~/.cursor/plugins/local/` filesystem copies as a shortcut. Per the install-surface lesson: marketplace plugins are layer-3-via-marketplace; the playbook's content is layer-3-via-agent-config.
- Some Tier-3 agents have no programmatic runtime-discovery surface (the playbook only writes their `AGENTS.md`). For those, layer-3 verification reduces to "the AGENTS.md is on disk and the agent picks it up on next session", and `--verify` simply confirms layer-2.
- For MCP servers, ADR-0036 layer-3 is "an entry in the agent's MCP config plus a running server process." v0.7's `--verify` covered the config-entry half. **v0.8 closes the running-process half** via `scripts/mcp_runtime_probe.py`: `cmd_verify` spawns each registered server, sends one JSON-RPC `initialize` request over stdio with a 10s timeout, and classifies the outcome as ok / fail / timeout / skipped (skipped = command path not yet bootstrapped, which is a layer-2 gap, not a runtime failure). The probe does not call any tools; that next step is out of scope.
- For skills, layer-3 runtime discovery means the agent's skill loader walks the materialization path in a NEW chat session. `make doctor-verify` confirms the materialization plus the `.playbook-owned` marker that the playbook re-install respects; the new-session step is operator workflow, not a check the offline tool can run. `skills/AGENTS.md` says this explicitly.

## Implementation

- `scripts/checks/hook_source_unification.py` -- layer-1 gate landed alongside this ADR.
- `tests/lifecycle/test_lifecycle.py::test_native_hook_config_after_install` -- parametrized layer-3 test across claude-code / codex / cursor / cline / windsurf, sharing `scripts/hook_native_config.py::parse_native_hook_commands` with `cmd_verify` so the two paths can not drift.
- `tests/lifecycle/test_lifecycle.py::test_native_skill_install_paths` -- parametrized layer-3 test for skill materialization paths across claude-code / codex / cursor / windsurf. Confirms `.playbook-owned` is present, which is the playbook's layer-2 ownership signal; true layer-3 loader discovery for skills additionally requires a new agent chat session and is out of scope for an offline check.
- `scripts/install.py --verify` and `make doctor-verify` -- layer-3 runtime UX. cmd_verify + verify_adapter live in `scripts/install_verify.py`; the adapter shape registry (config paths, event normalization, command-equality predicate) lives in `scripts/hook_native_config.py` and is the single source of truth shared with the lifecycle test suite.
- `scripts/mcp_runtime_probe.py` (v0.8) -- the JSON-RPC `initialize` probe used by cmd_verify to close the running-process half of MCP layer-3. Pure, side-effect-free per call (spawn + handshake + terminate); never raises; returns a typed `ProbeResult`.
- `hooks/README.md` "Three Layers" section + "hook not firing?" debug checklist.
- `skills/AGENTS.md` "Skill install surfaces" parallel section.

## Related

- ADR-0024 (Adapter Protocol + Install Manifest): defines how layer-2 is recorded.
- ADR-0027 (AGENTS.md document type + hook event metadata): layer-1 contract for hooks.
- ADR-0035 (canonical hook source unification): layer-1 contract for hook bodies; this ADR generalizes the discipline across all content types.
- v0.6 install-surface lesson (handoff doc `docs/human-html/2026-05-25-handoff-v0-6-multi-agent-hook-parity.html`).
