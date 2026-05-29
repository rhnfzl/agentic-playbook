# scripts/marketplace/manifests/

Per-platform manifest builders. Each module knows ONE vendor's schema and nothing else; the orchestrator in `scripts/marketplace/emitter.py` stays platform-agnostic.

## What each builder does for the user

Takes a role profile + the emitter config + the resolved content refs and produces a plugin manifest dict the orchestrator JSON-serializes to the right path. The shape differences are constrained by the four vendor schemas; the builder's job is to translate the same internal profile into each vendor's expected shape.

## Builders

| Builder | Output file(s) | Non-obvious constraint |
|---|---|---|
| `claude.py` | `.claude-plugin/plugin.json` + root-level `.claude-plugin/marketplace.json` | LOCAL source is a BARE STRING `"./<name>"`. Object source discriminators are `github`, `url`, `git-subdir`, `npm` only (no `local` discriminator). `agents` is a list of `.md` paths. `owner.name` is the PERSON, not the catalog handle. |
| `cursor.py` | `.cursor-plugin/plugin.json` + root-level `.cursor-plugin/marketplace.json` | Cursor's plugin schema is currently a strict subset of Claude's, so this file passthrough-re-exports the Claude builders. Future drift gets caught by changing only this file. |
| `codex.py` | `.codex-plugin/plugin.json` + root-level `.agents/plugins/marketplace.json` | The catalog lives at `.agents/plugins/marketplace.json` (Codex's repo-local discovery path), NOT `.codex-plugin/marketplace.json` (Codex does not read that). Plugin.json does NOT contain `policy`. Marketplace.json plugin entry uses `interface.displayName` instead of `owner`; the entry MUST include `policy.installation` (`AVAILABLE` / `NOT_AVAILABLE` / `INSTALLED_BY_DEFAULT`), `policy.authentication` (`ON_INSTALL` / `ON_USE` only; `NONE` is silently dropped by Codex), and `category`. Source is an OBJECT `{source:"local", path:"./<name>"}` (`local` IS a valid discriminator here). `git-subdir` uses `{url, path, ref?}`, not `{repo, subdir}`. |
| `gemini.py` | per-plugin `gemini-extension.json` | NO `author` field (not in the verified schema). `mcpServers` is the canonical place for MCP integration; the builder populates it from resolved MCP refs and handles both flat (`base/mcp/<name>.json`) and bundle (`base/mcp/<name>/server.json`) layouts. Gemini auto-discovers content from the extension root, so the manifest is metadata-only. |

## Shared helpers

`_shared.py` contains `_default_marketplace_description(profile)` (returns the profile description or a fallback) and `_plugin_readme(profile, version)` (renders the per-plugin README body the orchestrator writes outside the JSON loop).

## Verification dates

Each builder's docstring records the date the vendor schema was last verified against published docs. When a vendor releases a new schema version, re-verify the affected builder against the live docs and update the date.

Current verification dates (all 2026-05-28):

| Builder | Source |
|---|---|
| `claude.py` | `code.claude.com/docs/en/plugin-marketplaces` |
| `codex.py` | `developers.openai.com/codex/plugins/build` + `openai/codex` plugin-creator SKILL.md |
| `cursor.py` | `cursor.com/docs/plugins` + `github.com/cursor/plugins` |
| `gemini.py` | `geminicli.com/docs/extensions/reference` + `google-gemini/gemini-cli` docs |

## Related

- [`../README.md`](../README.md) for the orchestrator + package overview.
- [`docs/adr/0043-marketplace-emitter-for-personal-brand-distribution.md`](../../../docs/adr/0043-marketplace-emitter-for-personal-brand-distribution.md) for the design rationale across all four vendors.
