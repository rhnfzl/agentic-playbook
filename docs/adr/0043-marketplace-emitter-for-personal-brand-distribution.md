# 0043. Marketplace emitter for personal-brand distribution

## Status

Accepted (2026-05-28).

## Context

ADR-0042 introduced `scripts/sync_distribution.py`: an audited, scrubbed copy of `base/` from this repo to an external destination. That mechanism solves the "ship the portable subtree somewhere else" problem at the file level. It does not address the next question downstream: how does someone *install* what arrived at the destination?

Four vendor systems converged on a plugin-manifest pattern that lets agentic-tool users install curated content with one command instead of cloning and wiring by hand:

- **Claude Code:** `.claude-plugin/plugin.json` per plugin and `.claude-plugin/marketplace.json` per catalog. Users install with `/plugin install <plugin>@<catalog>`. (Reference: `code.claude.com/docs/en/plugin-marketplaces`.)
- **Cursor:** `.cursor-plugin/plugin.json` per plugin. Cursor's plugin schema is currently a strict subset of Claude's. (Reference: `cursor.com/docs/plugins`.)
- **Codex (OpenAI):** `.codex-plugin/plugin.json` per plugin and `<repo-root>/.agents/plugins/marketplace.json` for the catalog. Codex's marketplace entry shape differs from Claude's in important ways (nested source object, `policy.installation` + `policy.authentication` enums, `category` required, `interface.displayName` instead of `owner`). (Reference: `developers.openai.com/codex/plugins/build` + `openai/codex` plugin-creator skill.)
- **Gemini CLI:** `gemini-extension.json` at the extension root. Metadata-only manifest; Gemini auto-discovers content from the extension root. `mcpServers` is the canonical place for MCP integration. (Reference: `geminicli.com/docs/extensions/reference`.)

Without a marketplace emitter, the downstream destination is a pile of portable content that each user still has to wire by hand. With one, the same content becomes installable across all four vendor systems in a single emit pass.

A handful of design choices follow from the user-facing intent (open-source distribution under a personal brand) rather than from internal tooling:

### Constraint 1: catalog identity is personal-brand, not toolchain-internal

The catalog identifier appears in the install command (`/plugin install <plugin>@<catalog>`) so it is publicly visible to anyone who installs anything. The natural convention in the public ecosystem (`dashed/claude-marketplace`, `danielrosehill/Claude-Code-Plugins`, `just-be.dev`) is to use the maintainer's GitHub handle as the catalog identifier. This catalog uses `rhnfzl` to match `github.com/rhnfzl`.

### Constraint 2: vendor-schema accuracy or installs silently break

Anthropic publishes a reserved-names list that blocks catalog names containing the tokens `official`, `anthropic`, `claude` in official-sounding combinations and a list of fully reserved canonical names. Codex silently drops marketplace entries whose `policy.authentication` is not in the `{ON_INSTALL, ON_USE}` enum. Claude's local source is a bare string `"./<name>"` while Codex's local source is an object `{source:"local", path:"./<name>"}`. They look similar but are different shapes, and an emitter that confuses them produces invalid catalogs in one vendor or the other. Gemini's `gemini-extension.json` does NOT accept an `author` field (it's not in the verified schema). Each of these gotchas must be encoded in the emitter once so callers cannot bypass it.

### Constraint 3: profile-driven content filtering

A maintainer may want different plugins for different roles (`backend-developer`, `frontend-developer`, `tech-lead`, `devops`, etc.). The same `base/skills/...` source set should produce different plugin bundles based on which slugs each role profile includes. The emitter must read role-profile TOML files from `profiles/` and emit one plugin per profile, plus an `_all` meta-profile that union-aggregates them.

### Constraint 4: idempotency and stale cleanup

The emit step runs as a routine maintenance task downstream of the content sync. Re-running it on an unchanged source must produce zero new writes (so the destination's git history stays clean). Removing a ref from a profile must make the emit step remove the corresponding files from the destination on the next run (so a stale skill doesn't ship by accident).

### Constraint 5: operator identity stays outside the source repo

Forks and other catalogs will rebrand. The catalog identifier (`catalog_name`), the person's name (`author_name`), the optional email (`author_email`), and the destination path live in an operator-owned manifest file outside the repo (the existing pattern from ADR-0042 at `scripts/templates/distribution-manifest.example.toml`). The repo ships an example with `<your-catalog-handle>` placeholders, not literal personal identity.

## Decision

### Package: `scripts/marketplace/`

A navigable package with one orchestrator, four manifest builders, two aggregators, profile loading, content materialization, and an error hierarchy. The top-level public surface is six names: `emit`, `main`, `TOOL_VERSION`, `EmitterConfig`, the `Profile` union, and the `EmitError` hierarchy.

Module layout:

| Module | Responsibility |
|---|---|
| `errors.py` | EmitError + five subclasses with exit-code mapping. |
| `types.py` | `RoleProfile`, `MetaProfile`, `Profile` union, `EmitterConfig` (with `author_name` distinct from `catalog_name`), `ComponentSpec` table, `specs_for(profile)` filter. |
| `profile_loader.py` | Slug validation, reserved-name rejection, TOML parsing, meta-profile aggregation. |
| `content_ops.py` | `_resolve_profile` walker, flat-vs-bundle MCP layout resolver, materialization with content-based idempotency, path-safety predicate, stale-path cleanup with directory protection. |
| `hook_aggregator.py` | Per-profile `hooks/hooks.json` with `PLAYBOOK-HOOK-EVENT` header validation and actionable WARN lines. |
| `mcp_aggregator.py` | Per-profile `.mcp.json` with `mcpServers` dedup and actionable WARN lines on unparseable JSON. |
| `manifests/claude.py` | Claude `plugin.json` + `marketplace.json`. Local source is a bare string. `agents` is a list of `.md` paths. |
| `manifests/cursor.py` | Passthrough to Claude builders (Cursor's schema is a subset). |
| `manifests/codex.py` | Codex `plugin.json` WITHOUT `policy`; `marketplace.json` with nested-source object, `policy.installation` + `policy.authentication` + `category`, `interface.displayName` instead of `owner`. |
| `manifests/gemini.py` | `gemini-extension.json` with NO `author` field; `mcpServers` populated from resolved MCP refs. |
| `emitter.py` | Orchestrator: `_emit_plugin_directory` per profile, then `_emit_marketplace_manifests` ONCE with the full profile tuple. The split is load-bearing: writing root-level catalog manifests inside the per-profile loop would overwrite earlier profiles with the last one's plugin list. |

### Back-compat CLI shim

`scripts/marketplace_emitter.py` re-exports the public surface and forwards to `main()` so existing `python3 scripts/marketplace_emitter.py ...` invocations and existing imports keep working. The shim is a thin re-export plus a `__main__` guard.

### Facade for `sync_distribution.py`

`scripts/marketplace_config.py` exposes a `run_marketplace_emit(manifest, dry_run)` callable that takes a `_ManifestLike` protocol-typed input and constructs the `EmitterConfig`. `sync_distribution.py` calls the facade rather than importing from `marketplace` directly, so the package can refactor internals without breaking the sync caller.

### Author identity is distinct from catalog identity

`EmitterConfig.author_name` (the person's name, for example "Rehan Fazal") is a required CLI argument. `EmitterConfig.author_email` is optional. Every `author.name` and `owner.name` emitted into manifests goes through `config.author_block()`. The catalog identifier (`catalog_name`, for example "rhnfzl") is a separate argument and only appears as the marketplace `name`, the plugin source path prefix, and `interface.displayName`. The split prevents the catalog handle from being used as a person's name in emitted JSON.

### Exit-code carve-out

`scripts/sync_distribution.py` already documents an exit-code carve-out for marketplace safety failures (5). The emitter shares the carve-out: every error subclass declares an `exit_code` attribute and `main()` returns it. The CLI distinguishes "logical sync failure" (1) from "marketplace safety failure" (5) so a scheduled wrapper can react to each separately.

## Alternatives considered

### One emitter per vendor

A separate top-level script per vendor (Claude / Cursor / Codex / Gemini). Rejected because the four scripts would share the same profile loading, content resolution, hook aggregation, MCP aggregation, and idempotency story. Vendor-specific code is the manifest builder only.

### Monolithic single-file emitter

A single `~1500-line marketplace_emitter.py` matching the upstream playbook's first iteration. Rejected here because building it monolithic and then splitting it later wastes the work that produced the cleaner shape upstream; downstream sync starts at the polished package shape directly.

### Skip the marketplace step entirely

Let downstream users wire by hand from the synced content. Rejected because the marketplace step is the difference between "this is a folder of files" and "this is installable", and the user-facing wins (one-line installs, vendor-system integration, profile-driven role bundles) outweigh the implementation cost.

## Consequences

A new content type, plugin manifests, is owned by the playbook. Vendor schema drift becomes a maintenance task; the verified-against-docs date in each manifest builder's docstring records when the schemas were last validated and serves as the trigger for re-verification. The operator-manifest pattern adds one setup step at the destination (filling in `catalog_name`, `author_name`, `author_email`, `profiles_dir`).

Per-profile semver overrides give a tight version pin for each plugin, falling back to the configured default and then to the playbook's `VERSION` file. Read at runtime, so README examples cannot encode a literal version.

The supply-chain security gate (ADR-0047) and skill telemetry layer (ADR-0048) compose cleanly: emitter outputs are content the BOM scans, and emitter invocations themselves are not telemetry-instrumented (the emitter is a maintenance tool, not a per-skill runtime).

## References

- [ADR-0040](0040-base-overlay-subtree-split-for-content-tiering.md) for the base / overlay split that makes `base/` a clean distribution candidate.
- [ADR-0042](0042-playbook-content-distribution.md) for the content sync mechanism that delivers content to the destination before the marketplace step runs.
- [ADR-0047](0047-supply-chain-security-gate.md) for the supply-chain scanning that BOM-tracks emitter outputs.
- Claude Code plugin marketplace documentation: `code.claude.com/docs/en/plugin-marketplaces`.
- Codex plugin documentation: `developers.openai.com/codex/plugins/build`.
- Cursor plugin documentation: `cursor.com/docs/plugins`.
- Gemini CLI extension reference: `geminicli.com/docs/extensions/reference`.
