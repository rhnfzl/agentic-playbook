# scripts/marketplace/

The marketplace emitter package. Per ADR-0043.

## What this package does for the user

Takes the playbook's portable content (skills, rules, hooks, MCP configs, agents, commands, prompts) plus role profiles and produces per-vendor plugin catalogs (Claude Code, Cursor, Codex, Gemini) at an operator-configured destination. The destination becomes installable: end users run `/plugin install <plugin>@rhnfzl` instead of cloning and wiring by hand.

The catalog identity used by this repo is `rhnfzl` (matches the GitHub-owner namespace). Forks override via the operator manifest.

## Public surface

Import from `marketplace`:

| Name | Kind | Role |
|---|---|---|
| `emit` | function | Top-level emit entry point. Reads profiles, materializes content, writes manifests. |
| `main` | function | CLI entry point. Argparse + EmitterConfig construction + emit + exit code. |
| `TOOL_VERSION` | str | The playbook's `VERSION` at import time. Used as the default tool version on emitted manifests. |
| `EmitterConfig` | dataclass | Frozen configuration: `repo_root`, `dest_root`, `tool_version`, `author_name`, optional `author_email`, `dry_run`, `default_profile_version`. The `author_block()` helper is the single source for the `author` object across all manifest builders. |
| `RoleProfile` / `MetaProfile` / `Profile` | dataclass / Union | Profile shapes parsed from `profiles/*.toml`. `MetaProfile` is the auto-derived `_all` aggregate. |
| `EmitError` and subclasses | exception | Hierarchy carrying exit codes (1 for profile-load failures, 5 for safety failures). |

Nothing else is part of the stable surface. Internal helpers may move between modules without notice.

## Error model

| Exception | Exit code | When it fires |
|---|---|---|
| `ProfileLoadError` | 1 | Profile file missing, unreadable, or invalid TOML. |
| `SlugValidationError` | 5 | Catalog name or profile name violates the kebab-case slug shape. |
| `ReservedNameError` | 5 | Catalog name is on Anthropic's reserved list, or contains a reserved token (`official` / `anthropic` / `claude`) in an official-sounding combination. |
| `MaterializationError` | 5 | Writing a resolved path into the plugin directory failed (disk full, permission denied, etc.). |
| `PathSafetyError` | 5 | A plugin-relative destination path would escape the plugin directory after path resolution. |

The exit-code carve-out matches `sync_distribution.py`'s reserved 5-for-safety carve so a scheduled wrapper can distinguish logical failures from safety failures.

## Idempotency contract

Re-running emit on an unchanged source produces zero new writes. `_write_if_changed` reads the existing destination and skips when content matches; `_materialize` uses `filecmp.cmp(shallow=False)` for files and a recursive byte-level walk (`_trees_match`) for directories. Removing a ref from a profile makes the next emit remove the corresponding paths from the destination (`_remove_stale_plugin_content`); the protected-name list keeps emitted manifests intact during stale cleanup.

## Idempotency edge case: multi-profile root manifests

The root-level catalog manifests (`.claude-plugin/marketplace.json`, `.cursor-plugin/marketplace.json`, and `.agents/plugins/marketplace.json` for Codex) are written ONCE in `_emit_marketplace_manifests` after the per-profile loop, with the FULL profile tuple. Writing them inside the per-profile loop would let later profiles overwrite earlier ones; the post-loop write is load-bearing. (Codex discovers repo-local catalogs at `.agents/plugins/marketplace.json`, not `.codex-plugin/`.)

## Extension recipe: add a new content type

1. Add a new value to `Literal[...]` in `ComponentSpec.kind` (in `types.py`).
2. Add a new `ComponentSpec(...)` row to `COMPONENT_SPECS`.
3. Add a matching attribute to `RoleProfile` (`tuple[str, ...]` defaulting to `()`).
4. Add the attribute to `_load_profile`'s `_list("<section>")` lookups (`profile_loader.py`).
5. If the type needs custom destination logic (like MCP's flat-vs-bundle), extend `_plugin_rel_for` in `content_ops.py`.
6. If the type needs aggregation, add an aggregator module mirroring `hook_aggregator.py` or `mcp_aggregator.py` and wire it into `_emit_plugin_directory` in `emitter.py`.
7. Add contract tests to `tests/lifecycle/test_marketplace_package.py`.

## Extension recipe: add a new vendor (platform)

1. Create `manifests/<vendor>.py` exporting `_<vendor>_plugin_manifest(profile, config)` and either `_<vendor>_marketplace_manifest(profiles, config, resolved_by_profile, catalog_name)` if the vendor has a catalog file or a per-extension manifest builder if the vendor's pattern is per-extension only.
2. Cite the vendor's schema docs URL and the validation date in the module docstring.
3. Add an entry to `_PLUGIN_MANIFEST_WRITES` in `emitter.py` for the per-plugin manifest.
4. If the vendor has a catalog file, add an entry to `_MARKETPLACE_WRITES` for it. Otherwise call the per-extension builder inside `_emit_plugin_directory` next to where Gemini's `gemini-extension.json` is written.
5. Add a row to `manifests/README.md` with the schema constraints worth knowing.
6. Add contract tests pinning the vendor-specific shape constraints (any required fields, any enum values, any forbidden fields).

## How `make` consumes this

```
  sync_distribution.py
        |
        +-- after content sync completes, calls
            marketplace_config.run_marketplace_emit(manifest, dry_run)
                |
                +-- marketplace.emit(config, profiles_dir, catalog_name)
                        |
                        +-- profile_loader._load_profiles
                        +-- for profile in profiles:
                        |     _emit_plugin_directory
                        |         materialize + hook_aggregator + mcp_aggregator
                        |         _PLUGIN_MANIFEST_WRITES table loop
                        |         per-plugin README + emitted-by sidecar + gemini-extension
                        |         _remove_stale_plugin_content
                        +-- _emit_marketplace_manifests
                              _MARKETPLACE_WRITES table loop (once, with full profile tuple)
```

The marketplace_emitter.py shim re-exports the public surface so `python3 scripts/marketplace_emitter.py --help` continues to work for direct CLI use.

## Catalog identity

Catalog identity lives in the operator manifest (`scripts/templates/distribution-manifest.example.toml`), not in the source. The example ships with `<your-catalog-handle>` placeholders so forks adopt the structure without scrubbing.

This repo's maintainer uses catalog name `rhnfzl` and author name `Rehan Fazal`. The split matters: `catalog_name` is the public namespace seen on install commands; `author_name` is the person behind the catalog, which goes into emitted `author{}` and `owner{}` blocks.

## Related

- [`docs/adr/0043-marketplace-emitter-for-personal-brand-distribution.md`](../../docs/adr/0043-marketplace-emitter-for-personal-brand-distribution.md) for the full design rationale.
- [`docs/adr/0042-playbook-content-distribution.md`](../../docs/adr/0042-playbook-content-distribution.md) for the sync mechanism that delivers content to the destination before the marketplace step.
- [`manifests/README.md`](manifests/README.md) for the per-platform schema details.
- [`tests/lifecycle/test_marketplace_package.py`](../../tests/lifecycle/test_marketplace_package.py) for the contract test suite.
- `scripts/marketplace_emitter.py` for the back-compat CLI shim.
- `scripts/marketplace_config.py` for the facade used by `sync_distribution.py`.
