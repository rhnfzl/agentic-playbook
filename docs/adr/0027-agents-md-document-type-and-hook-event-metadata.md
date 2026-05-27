# 0027. AgentsMd document type + canonical Hook source with explicit event metadata

## Status

Accepted (2026-05-25); landed in v0.4.

Partially superseded by ADR-0033 (v0.5: AgentsMd as canonical write API + materialize_rules deprecation). ADR-0033 extends the AgentsMd type with write methods so the same document type owns both read and write paths.

## Context

This ADR captures two adjacent decisions from the grilling session that have shared underlying motivation: making document and hook metadata explicit and locally readable instead of implicit and inferred.

### AGENTS.md handling

Through v0.3, AGENTS.md was touched in five places with five different mental models:

- `scripts/check_agents_md.py` - regex-based governance checks
- `scripts/playbook_init.py` - string interpolation for the 8-section scaffold
- `scripts/playbook_update.py` - regex substitution for pointer + last_reviewed
- `scripts/adapters/_loader.py` - generic `upsert_managed_block` (also used for non-AGENTS.md files)
- Per-Adapter callers using the managed-block helper directly

No shared type. The 8-section template from ADR-0013 was effectively a documentation convention with regex enforcement, not a parseable schema.

### Hook event registration

Through v0.3, the Claude Code adapter inferred each hook's event (`PreToolUse` / `PostToolUse` / `Stop`) from filename substring matches: anything containing `pre` / `guard` / `never` became `PreToolUse`; `post` / `autoindex` / `advisory` became `PostToolUse`; etc. The inference function had no `SessionStart` mapping, so `agent-memory-session-brief.sh` silently registered to `PostToolUse` even though the script's own docstring and the README documented it as `SessionStart`. Multiple other hooks (`sonar-advisory`, `human-html-advisory`) had drift between the README's claimed event and the inferred event.

Additionally, the human-html skill ship its own copies of two hooks at `skills/meta/human-html/hooks/`, divergent from the root `hooks/` copies the playbook installer materialized. The richer skill-local versions (Codex `apply_patch` awareness, command-text filtering) never reached production.

## Decision

### AgentsMd document type

A new `scripts/agents_md.py` module exports the `AgentsMd` dataclass plus parse / render / mutate / validate methods:

```python
@dataclass(frozen=True)
class AgentsMd:
    frontmatter: dict[str, str]
    pointer: str | None
    sections: list[Section]
    raw: str

    @classmethod
    def parse(cls, text: str) -> "AgentsMd": ...
    @classmethod
    def load(cls, path: Path) -> "AgentsMd": ...

    def render(self) -> str: ...
    def with_refreshed_pointer(self, playbook_root: Path) -> "AgentsMd": ...
    def with_last_reviewed(self, today: str) -> "AgentsMd": ...
    def validate(self, required_sections: list[str] | None) -> list[ValidationIssue]: ...
    def section(self, heading: str) -> Section | None: ...
```

Parse is best-effort: malformed input still produces an AgentsMd with whatever was recoverable. Round-trip via `.render()` is lossless on the original raw text; mutation methods return new instances with updated raw. `ValidationIssue` severity values (`warn` / `fail`) match the `CheckResult` vocabulary from ADR-0024 sibling Candidate 5 so check_agents_md can route AgentsMd.validate() results directly without translation.

Generic managed-block utilities (`upsert_managed_block`, `remove_managed_block`) stay in `_loader.py` since they operate on non-AGENTS.md files too (settings.json, codex config.toml). AgentsMd uses them as primitives.

First consumer: `scripts/playbook_update.py` drops its bespoke regex passes in favor of `doc.with_refreshed_pointer().with_last_reviewed(today)`. Other consumers (check_agents_md, playbook_init, adapter managed-block callers) can migrate incrementally; the type exists so they have something to migrate to.

### Canonical Hook source + explicit event metadata

Root `hooks/` is the canonical hook location. Skill-local hook copies (the two under `skills/meta/human-html/hooks/`) are deleted. Where they were genuinely richer (the divergent `human-html-autoindex.sh`), the richer version is promoted to root first.

Each hook script carries an explicit `# PLAYBOOK-HOOK-EVENT:` header line in the first ~15 lines:

```bash
#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# (rest of header comment + script body)
```

The `claude_code` adapter parses the header with one regex (`^#\s*PLAYBOOK-HOOK-EVENT:\s*(\w+)\s*$`). If the header is missing, the adapter falls back to filename-based inference (deprecated; retained for back-compat). Supported events: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`.

Initial migration: all 8 root hooks ship with the explicit header. Filename inference is now a deprecated fallback and can be removed in a follow-up once metadata is universal.

## Consequences

### AgentsMd

- Each consumer that handles AGENTS.md can share one type instead of writing its own parse logic. `playbook_update.py` is the demonstration consumer in this PR.
- The 8-section template (ADR-0013) becomes a validation rule (`AgentsMd.validate()`) instead of an implicit convention.
- Round-trip is byte-identical, so callers can safely parse-mutate-write without losing whitespace or formatting.
- `ValidationIssue` directly composes into `CheckResult` so check_agents_md's eventual checks/agents_md.py form is a thin delegation.

### Hook canonicalization

- Hook bug fix: `agent-memory-session-brief.sh` now registers to `SessionStart` instead of the wrong `PostToolUse` it had been silently classified as.
- Hook event drift between README and adapter inference is eliminated for all 8 hooks (lint-guard, sonar-advisory now correctly PostToolUse per their actual code; human-html-advisory correctly PreToolUse).
- The richer `human-html-autoindex.sh` (Codex `apply_patch` awareness, Bash command-text filtering, gallery loop guard) finally reaches production.
- The two-location source-of-truth drift problem for human-html hooks is closed (root `hooks/` is canonical; the human-html skill's SKILL.md links back).

## Rejected alternatives

### AgentsMd type

- **Lift managed-block + pointer helpers only.** Smallest change; each consumer still has its own AGENTS.md mental model. Doesn't unlock new behavior like section-aware validation.
- **Two types: AgentsMdHeader (parsed) + AgentsMdBody (opaque).** Compromise; section-aware validation still needs more work. Worth it only if full parse is genuinely too costly, which it is not (the 8-section template is structurally simple).

### Hook event metadata

- **YAML-ish frontmatter block at top of script.** Multi-line `# ---\n# event: ...\n# ---`. More structured if many fields are needed later, but YAML-in-shell-comments is ugly and the parser becomes more than a regex.
- **Central registry (`hooks/REGISTRY.toml`).** Single source of truth in one place. Cost: adding a hook requires editing TWO files (script + registry). Drift between script existence and registry entry is silent.
- **Sidecar file per hook (`lint-guard.sh.meta`).** Doubles the file count; no clear advantage over the comment header.
- **Bundle into a `Skill` (hooks become Skill-owned).** Contrives a Skill home for the 6 orphan hooks (lint-guard, never-push-to-develop, etc.) that aren't conceptually part of any workflow.

## Related

- ADR-0007 (CLAUDE.md vs AGENTS.md vs SKILL.md): the AGENTS.md role is unchanged; this ADR adds a typed representation of it.
- ADR-0013 (AGENTS.md governance harness): the 8-section template is now enforceable via `AgentsMd.validate()` instead of bespoke regex.
- ADR-0024 (Adapter Protocol): the `materialize_rules` helper is the writer-side primitive; AgentsMd is the reader / validator counterpart.
- ADR-0033 (v0.5: AgentsMd as canonical write API): extends AgentsMd to own the writer-side path too; deprecates `materialize_rules`.
- Source: 2026-05-25 grilling session captured in `docs/human-html/2026-05-25-architecture-coding-agents-playbook-architecture-opportunities.html`.
