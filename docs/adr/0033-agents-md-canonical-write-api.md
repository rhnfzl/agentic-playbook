# 0033. AgentsMd as canonical write API + materialize_rules deprecation (supersedes parts of ADR-0027)

## Status

Accepted (2026-05-25); landed in v0.5. Partially supersedes ADR-0027 (the AgentsMd reader/writer split it left in place).

## Context

ADR-0027 introduced `AgentsMd` as a parse / render / validate document type with one consumer (`playbook_update.py`). The writer-side path (composing rules into a managed block + upserting into AGENTS.md) still went through the `materialize_rules` helper in `scripts/adapters/_writer.py`. Ten adapter call sites used `materialize_rules` directly. AgentsMd was the reader; `materialize_rules` was the writer. Two types for one document.

That split was fine for v0.4 because AgentsMd's value (parse + validate + pointer refresh) was orthogonal to managed-block writing. The v0.5 grilling reopened it because TargetMaterializer (ADR-0028) also writes AGENTS.md managed blocks, and forking the write path again would have left three callers for the same operation. Better to close the reader/writer loop on one type.

## Decision

Extend AgentsMd with four new methods so it owns both read and write paths:

- `AgentsMd.empty()` - starting point when the AGENTS.md file does not yet exist
- `AgentsMd.load_or_empty(path)` - load from disk if present, else empty()
- `with_managed_rules(rules, *, label=None, comment_style="html")` - return a new AgentsMd whose `raw` has the managed block updated (inserted, replaced, or appended)
- `save_to(path)` - write `render()` to disk; return one of `"created" | "unchanged" | "replaced"`

Adapter call sites convert from `materialize_rules` to the AgentsMd fluent chain:

```python
# before (v0.4)
action = _loader.materialize_rules(content.rules, path, label="claude-code")

# after (v0.5)
action = (
    AgentsMd.load_or_empty(path)
    .with_managed_rules(content.rules, label="claude-code")
    .save_to(path)
)
```

10 adapter call sites updated: claude_code, codex, cursor, copilot, aider, windsurf, cline, gemini_cli, plus the 20 Tier 3 instances sharing tier3's install body. `materialize_rules` is retained as a 2-line shim that lazy-imports AgentsMd and delegates; new code goes through AgentsMd directly.

### Side effect: tier3 rename

`scripts/adapters/agents_md.py` (the Tier 3 module) was renamed to `scripts/adapters/tier3.py` to resolve the naming collision with the top-level `scripts/agents_md.py` document type module. The Tier 3 module's role is "Tier 3 AGENTS.md adapter" which `tier3.py` expresses more clearly, and the rename eliminates a Pyright resolution ambiguity the sweep made acute.

### Status vocabulary change

`save_to()` returns `"created" | "unchanged" | "replaced"`. The v0.4 `materialize_rules` returned `"created" | "replaced" | "appended" | "unchanged"`; the "appended" case (file existed but had no managed block) now maps to "replaced" because `save_to` compares whole-file content. Cosmetic difference in the log line; managed-block output is byte-identical for unchanged rules.

## Consequences

### Good

- A single canonical write API for AGENTS.md. Adapters all speak the same language; reviewers reading multiple adapters see the same pattern.
- `AgentsMd` is the searchable entry point when someone asks "where is AGENTS.md mutated in this codebase?"
- TargetMaterializer (ADR-0028) inherits the same write API for free; managed-block output is consistent across home install + target install.

### Bad

- `materialize_rules` becomes a thin shim. Callers should prefer AgentsMd directly; the shim exists for backward compat with any external consumer that imports it.
- One status value (`"appended"`) is dropped from the vocabulary. Adapters that pattern-matched on it for log output collapse to `"replaced"`. No semantic impact on the file, only on the operator's display.

## Related

- ADR-0027 (AgentsMd document type + canonical Hook source): the parent decision; this ADR extends it.
- ADR-0028 (TargetMaterializer): consumes the new AgentsMd write API for per-project AGENTS.md generation.
- Source: 2026-05-25 grilling session captured in `docs/human-html/2026-05-25-architecture-coding-agents-playbook-architecture-opportunities.html`.
