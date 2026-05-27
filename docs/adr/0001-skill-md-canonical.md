# 0001. SKILL.md as the canonical source format

## Status
Accepted (2026-05-24)

## Context

The playbook needs a source format for workflow recipes. Multiple coding agents read different files:
- Claude Code: SKILL.md with YAML frontmatter
- Codex: skills/<name>/SKILL.md (same shape)
- Cursor: .cursor/rules/*.mdc (different shape, but no skill concept)
- Windsurf: .windsurf/rules/*.md (different)

We need ONE canonical format that the installer can compile to each target. Three candidates:
1. Adopt mattpocock's SKILL.md (proven, used by Claude Code natively).
2. Invent a custom schema (more expressive, reinvents a wheel).
3. Use plain markdown with no metadata (loses trigger semantics).

## Decision

Adopt SKILL.md as the canonical source format. Each skill is a directory under `skills/<category>/<name>/` containing a `SKILL.md` with YAML frontmatter:

```yaml
name: <slug>
description: <one sentence, third-person, starts with "Use when ...">
version: 0.1.0
owner: <VCS-handle>
last_reviewed: YYYY-MM-DD
tags: [<3-5 relevant tags>]
scope: [<ai-backend|mcp|any>, ...]
```

The body follows: trigger conditions, procedure, output shape, "when NOT to use this skill."

## Consequences

- Compatible with Claude Code natively (no translation needed for Tier 1).
- Cursor and Windsurf adapters must translate SKILL.md to their formats (.mdc, .windsurf/rules/*.md). This is the cost of using SKILL.md as canonical: Cursor/Windsurf users get translated content, not native skills.
- Frontmatter validation (`make check`) keeps the schema enforced.
- `last_reviewed` enables decay tracking (warn at 90d, block at 180d).

## Alternatives considered

- **Custom schema**: rejected. mattpocock's format is battle-tested at 18 skills + community adoption. Reinventing it adds risk without benefit.
- **Plain markdown**: rejected. Loses trigger semantics (`description` is how Claude Code routes to the skill at runtime).

## Source

mattpocock/skills proved the SKILL.md format works at scale (18 skills, ~100k stars). Block/Goose uses a richer JSON-based Recipes format; we opted for SKILL.md instead because it is more git-friendly and matches what team already uses in `~/.agents/skills/`.
