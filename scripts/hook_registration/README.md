# scripts/hook_registration/

Per-shape hook emitters. Each shape module knows ONE host agent's native hook-configuration format and the cross-agent translation rules it implements.

## What this package does for the user

The playbook keeps hook content in a canonical source-of-truth shape (under `base/hooks/` and `base/skills/<cat>/<name>/hooks/` per ADR-0035). Different coding agents expose different native hook surfaces: Claude Code uses `hooks.json` with an event-keyed structure, Cursor uses an `.mdc` rules-folded shape, Windsurf has its own format. This package emits each per-host-agent native shape from the canonical source so Tier 1 adapters do not have to know the cross-agent translation rules themselves.

## The three shapes

Three shape emitters today, each in a self-contained module:

| Module | Host agent | Native format | Cross-agent translation rule |
|---|---|---|---|
| [`_claude_shape.py`](_claude_shape.py) | Claude Code | `hooks/hooks.json` keyed by `PreToolUse` / `PostToolUse` / `SessionStart` / `Stop` events. Each event holds a list of `{type, command, matcher?}` entries. | `PLAYBOOK-HOOK-EVENT` header in the hook script picks the event key. `PLAYBOOK-HOOK-MATCHER` header (optional) populates the `matcher` field. |
| [`_cursor_shape.py`](_cursor_shape.py) | Cursor | Cursor folds hooks into the rules surface (no separate hooks config). | The emitter wraps each canonical hook as a Cursor rule entry with a behavior directive that mirrors the source script's intent. |
| [`_windsurf_shape.py`](_windsurf_shape.py) | Windsurf | Windsurf's native shape mirrors Claude's event-keyed structure but with its own `pre_tool_use` / `post_tool_use` naming convention. | The emitter maps Claude's CamelCase events to Windsurf's snake_case + writes to the Windsurf-native location. |

Codex is intentionally NOT a separate shape: Codex's hook config is Claude-compatible with one auto-promote rule for `PreToolUse` documented in [ADR-0034](../../docs/adr/0034-cross-agent-hook-contract.md). The Codex adapter (`scripts/adapters/codex.py`) handles the auto-promote inline and consumes `_claude_shape.py` for the rest.

`_common.py` holds the parsing helpers each shape emitter shares (header extraction, validation, the canonical `HookEntry` dataclass).

## How to add a new shape

1. Create `scripts/hook_registration/_<host>_shape.py` exposing a `build(profile_hooks, target_path) -> list[InstalledPath]` callable.
2. Document the cross-agent translation rule the new shape implements: what does the host agent's native format look like, and how does the canonical source map into it?
3. Re-use `_common.py` helpers where possible (header parsing, dataclass) to keep the conversion semantics consistent across shapes.
4. Add a row to the table above. **Count the rows when you write the heading**: if a fourth shape lands and the heading still says "The three shapes", that is a documentation bug.
5. Wire the new shape into the adapter that consumes it. Adapters call shape emitters by name, not via dynamic dispatch, so the addition surfaces in adapter code review.

## How emitters compose with adapters

```
  base/skills/<cat>/<name>/hooks/*.sh         (canonical source)
        |
        | PLAYBOOK-HOOK-EVENT / PLAYBOOK-HOOK-MATCHER headers
        v
  scripts/hook_registration/_common.py        (parse + validate)
        |
        v
  per-shape emitter (this directory)          (vendor-native shape)
        |
        v
  Tier 1 adapter                              (writes native location)
```

The shape emitter never writes to disk directly. It returns `InstalledPath` records the adapter writes; the split keeps file-system effects auditable.

## Related

- [`docs/adr/0027-agents-md-document-type-and-hook-event-metadata.md`](../../docs/adr/0027-agents-md-document-type-and-hook-event-metadata.md) for the `PLAYBOOK-HOOK-EVENT` / `PLAYBOOK-HOOK-MATCHER` metadata contract.
- [`docs/adr/0029-hook-reconciliation-and-matcher-header.md`](../../docs/adr/0029-hook-reconciliation-and-matcher-header.md) for the matcher header + reconciliation pattern.
- [`docs/adr/0034-cross-agent-hook-contract.md`](../../docs/adr/0034-cross-agent-hook-contract.md) for the cross-agent contract (event names, matcher semantics, auto-promote rule).
- [`docs/adr/0035-canonical-hook-source-unification.md`](../../docs/adr/0035-canonical-hook-source-unification.md) for the canonical-source-of-truth pattern that pins skill-owned hooks under `base/skills/<cat>/<name>/hooks/` with root symlinks back.
- [`docs/adr/0037-generalized-hook-adapter-scoping.md`](../../docs/adr/0037-generalized-hook-adapter-scoping.md) for the scope contract that says Tier 1 adapters get hook surface and Tier 2 / 3 do not.
- [`scripts/adapters/README.md`](../adapters/README.md) for the adapter side of the contract.
