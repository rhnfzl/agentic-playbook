# 0031. _loader.py four-file split

## Status

Accepted (2026-05-25); landed in v0.5.

## Context

Through v0.4, `scripts/adapters/_loader.py` grew to 887 lines mixing seven responsibilities:

1. Typed contracts (Skill, Rule, Hook, McpConfig, Agent, Command, Prompt, InstalledPath, PlaybookContent NamedTuples)
2. The Adapter Protocol (interface every adapter implements)
3. Content scanners (load_skills, load_rules, load_hooks, load_mcp_configs, load_agents, load_commands, load_prompts)
4. Detection helpers (which, vscode_extension_present)
5. Target resolution (resolve_target, _validate_target, _prompt_for_target)
6. File writes (copy_skill_payload, materialize_mcp_sources, agent_to_toml, materialize_rules, upsert_managed_block, remove_managed_block, existing_toml_tables_outside_block)
7. Managed-block primitives + style lint helpers (find_em_dashes)

ADR-0024 (Adapter Protocol) gestured at a split. v0.5 work (TargetMaterializer in ADR-0028, hook reconciliation in ADR-0029, AgentsMd sweep in the ADR-0027 extension) all touch this file. Splitting first keeps each subsequent change reviewable in isolation; a v0.5 commit that adds 100 lines to TargetMaterializer should not also be a moving-887-lines-around commit.

The grilling reviewed three split granularities (3-file, 4-file, 5-file). 4-file won on the "what would someone deleting this file expect to find next to it" test.

## Decision

Split `_loader.py` into four sibling modules under `scripts/adapters/`. The old `_loader.py` becomes a re-export shim so existing adapter imports (`from ._loader import Adapter, InstalledPath, PlaybookContent`) keep working without touching adapter code.

### `_protocol.py` (typed contracts + cross-adapter primitives)

- `MARKER_ID` constant
- NamedTuples: `Skill`, `Rule`, `Hook`, `McpConfig`, `Agent`, `Command`, `Prompt`, `InstalledPath`
- `PlaybookContent` (with a lazy-import `.load()` classmethod that calls `_reader`)
- `Adapter` Protocol
- `reconcile_managed_json_mcp` function (and, in commit 6, `reconcile_managed_hook_commands`)

Why here: every adapter imports the types. Other modules can grow without disturbing the type surface.

### `_reader.py` (content scanners)

- `_parse_frontmatter`
- `load_skills`, `load_rules`, `load_hooks`, `load_mcp_configs`, `load_agents`, `load_commands`, `load_prompts`

Why here: pure read paths over the playbook repository tree. No writes. No filesystem mutations.

### `_detect.py` (detection + target resolution)

- `which` (PATH probe)
- `vscode_extension_present` (~/.vscode/extensions probe)
- `resolve_target`, `_validate_target`, `_prompt_for_target`

Why here: read-only probes of the user's machine (distinct from `_reader.py` which reads the playbook repo). Target resolution lives with detection because it interacts with the same user-machine surface.

### `_writer.py` (file writes + composition + style lint)

- File writes: `copy_skill_payload`, `materialize_mcp_sources`, `agent_to_toml`, `upsert_managed_block`, `remove_managed_block`, `existing_toml_tables_outside_block`, `ensure_dir`
- Composition: `compose_agents_md`, `materialize_rules` (now a thin shim to AgentsMd per ADR-0027 extension)
- Constants used at write time: `AGENT_SHARED_MCP_DIR`, `AGENT_SHARED_PLACEHOLDER`, `PLAYBOOK_TARGET_PLACEHOLDER`, `MCP_BUNDLE_SKIP_NAMES`
- Style lint: `find_em_dashes`, `_EM_DASH_CHARS`

Why here: everything that mutates the filesystem or composes text destined for one. The style lint helpers live with writes because they operate on the text content being composed.

### `_loader.py` (re-export shim)

The 887-line file becomes a small re-export module:

```python
from ._protocol import *
from ._reader import *
from ._detect import *
from ._writer import *
```

(In practice we use explicit re-exports + an `__all__` list, not star imports, to keep the symbol surface explicit.)

Why keep `_loader.py` at all: 10 adapter modules import `from ._loader import Adapter, InstalledPath, PlaybookContent`. Renaming all those imports in one commit would be heavy. The shim absorbs the diff cost; new code is encouraged to import directly from the focused submodule.

## Consequences

### Good

- Each split file has one clear responsibility. `_writer.py` is what the TargetMaterializer needs to compose with; `_protocol.py` is what an external Codex review needs to read to understand the contract; `_reader.py` is where you grep when content loading misbehaves.
- The 887-line file becomes four files at 130-400 lines each. Cognitive load per-file drops noticeably.
- v0.5 commits that add new behavior (hook reconciliation, TargetMaterializer) land in the right file by construction. Reviewers see narrower diffs.
- The re-export shim means adapter code does not change. Future cleanup can migrate adapter imports to the focused modules incrementally.

### Bad

- Four files where there was one. Search-and-jump tooling has to know to look in all four when answering "where is `copy_skill_payload` defined?" Modern editors handle this fine; grep does too.
- `PlaybookContent.load()` needs a lazy import of `_reader` (the type is defined in `_protocol.py`, the loaders live in `_reader.py`). The lazy import is a small concession to module independence; the alternative was to move `PlaybookContent` itself, which would have spread the type across modules.
- Pyright reports false-negative imports for the re-export shim when scanning modules independently (it does not always resolve `from ._loader import X` when `X` is re-exported from `_writer.py`). Runtime imports work; the warnings are noise. Future work could add a `pyrightconfig.json` with explicit re-export rules.

## Implementation note

`scripts/adapters/_loader.py` is the only file external code references; nothing else changes. The split happened in commit 1 of the v0.5 PR; later commits (AgentsMd sweep, hook reconciliation, TargetMaterializer) land in the appropriate split file.

`_protocol.py` has the strongest backward-compatibility constraint: any change to NamedTuple field order or Adapter Protocol signature is a breaking change for every adapter. Treat it as the contract layer.

`_writer.py` has the most internal complexity. If a future split is needed, the natural next cut would be `_managed_block.py` (just upsert_managed_block + remove_managed_block + existing_toml_tables_outside_block) split out, leaving `_writer.py` focused on content writes.
