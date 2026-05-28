# scripts/adapters/

Per-agent adapter modules. Each adapter knows how to materialize the playbook's content into one coding-agent's native configuration shape.

## What this package does for the user

`make install` invokes the dispatcher in `scripts/install.py`, which discovers every adapter in this package and runs the ones whose `detect()` returns True for the user's machine. Each adapter then writes that user's installed playbook content into the per-agent native location: `~/.claude/` for Claude Code, `~/.codex/` for Codex, `~/.cursor/` for Cursor, and so on.

The Adapter Protocol means installer code never branches on "if claude_code, do X". Adding a new agent is one new module here plus one registration line.

## Adapter Protocol contract

Defined in [`_protocol.py`](_protocol.py). Every adapter exports:

```python
class Adapter(Protocol):
    name: str
    tier: int
    def detect(self) -> bool: ...
    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]: ...
```

`PlaybookContent` (also in `_protocol.py`) is the pre-loaded inventory of the eight content types (skills, rules, hooks, mcp, agents, commands, prompts, trajectories) that the dispatcher hands every adapter. The dispatcher uses `resolve_content_paths` (lives in `_protocol.py`, NOT `_reader.py`) to compute the per-adapter content set.

## Tier breakdown (by adapter constant, not by feature surface)

Tier source-of-truth is the `tier = N` constant declared inside each adapter module. Do not classify adapters by "what surface they materialize" (the constants ARE the contract).

| Tier | Module | `tier =` line |
|---|---|---|
| 1 | `claude_code.py` | `tier = 1` |
| 1 | `codex.py` | `tier = 1` |
| 1 | `cursor.py` | `tier = 1` |
| 1 | `windsurf.py` | `tier = 1` |
| 2 | `aider.py` | `tier = 2` |
| 2 | `cline.py` | `tier = 2` |
| 2 | `copilot.py` | `tier = 2` |
| 2 | `gemini_cli.py` | `tier = 2` |
| 2 | `pi.py` | `tier = 2` |
| 3 | (declarative) | 20 entries in `tier3.toml` produce `TierThreeAdapter` instances via `tier3.py`. Per ADR-0030. |

Tier semantics (per [ADR-0005](../../docs/adr/0005-tier-1-2-3-agent-support.md)):

- **Tier 1**: full content surface (skills, rules, hooks, MCP, agents, commands, prompts) + native hook config + native MCP config.
- **Tier 2**: subset surface (typically rules-only or rules + MCP) with no native hook config because the host agent does not expose a hook hook point.
- **Tier 3**: AGENTS.md-only via the declarative TOML registry. New entries add a row to `tier3.toml` rather than a new Python module.

## Shared helpers

| Module | Role |
|---|---|
| [`_reader.py`](_reader.py) | `load_skills`, `load_rules`, `load_hooks`, `load_mcp_configs`, `load_agents`, `load_commands`, `load_prompts`. Frontmatter parsing for every content type. |
| [`_writer.py`](_writer.py) | `copy_skill_payload`, `materialize_mcp_sources`, `merge_managed_mcp_into_json`, `upsert_managed_block`, `agent_to_toml`, `safe_symlink_or_copy` (Windows fallback), `expand_agent_shared_placeholder`. |
| [`_detect.py`](_detect.py) | `which`, `vscode_extension_present`, `resolve_target`. Cross-platform detection primitives. |
| [`_protocol.py`](_protocol.py) | Typed contracts (`Skill`, `Rule`, `Hook`, `McpConfig`, `Agent`, `Command`, `Prompt`, `InstalledPath`, `PlaybookContent`) + the `Adapter` Protocol + `reconcile_managed_json_mcp` / `reconcile_managed_hook_commands` + `resolve_content_paths`. |
| [`_loader.py`](_loader.py) | Re-export shim that preserves the pre-decomposition import surface from ADR-0031's `loader.py` four-file split. |

## Hook contract

Hooks are scoped to Tier 1 adapters. The cross-agent hook contract lives in [ADR-0034](../../docs/adr/0034-cross-agent-hook-contract.md) and [ADR-0035](../../docs/adr/0035-canonical-hook-source-unification.md). Each Tier 1 adapter knows how to translate the canonical shape into its host agent's native format; the shape emitters live in [`scripts/hook_registration/`](../hook_registration/).

## How to add a new adapter

1. Create `scripts/adapters/<name>.py` with the Adapter Protocol contract (`name`, `tier`, `detect`, `install`).
2. Choose the tier honestly: Tier 1 needs full surface + native hook config; Tier 2 takes the rules + optional MCP shape; Tier 3 goes through `tier3.toml` instead of Python.
3. Register the new adapter by importing it into `scripts/adapters/__init__.py:ALL_ADAPTERS`. THE REGISTRATION SEAM IS THE PACKAGE INIT, NOT ANYTHING INSIDE `install.py`. The dispatcher in `install.py` imports `ALL_ADAPTERS` from here.
4. Add a row to the Tier breakdown table above.
5. Run `make test` (covers adapter idempotency, target safety, content preservation).
6. Add lifecycle tests under `tests/lifecycle/test_<adapter>.py` for adapter-specific behaviors.

## Related

- [`docs/adr/0024-adapter-protocol-and-install-manifest.md`](../../docs/adr/0024-adapter-protocol-and-install-manifest.md) for the Adapter Protocol design rationale.
- [`docs/adr/0030-tier3-declarative-toml-registry.md`](../../docs/adr/0030-tier3-declarative-toml-registry.md) for the Tier 3 declarative pattern.
- [`docs/adr/0031-loader-py-four-file-split.md`](../../docs/adr/0031-loader-py-four-file-split.md) for the four-file split rationale (`_reader` / `_writer` / `_detect` / `_protocol` + `_loader` re-export shim).
- [`docs/adr/0034-cross-agent-hook-contract.md`](../../docs/adr/0034-cross-agent-hook-contract.md) and [`docs/adr/0035-canonical-hook-source-unification.md`](../../docs/adr/0035-canonical-hook-source-unification.md) for the hook contract.
- [`scripts/install.py`](../install.py) for the dispatcher that uses `ALL_ADAPTERS`.
- [`scripts/hook_registration/README.md`](../hook_registration/README.md) for the per-shape hook emitters Tier 1 adapters use.
