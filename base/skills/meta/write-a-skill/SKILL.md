---
name: write-a-skill
description: Use when creating a new agent skill, covering requirements gathering, SKILL.md authoring, file structure decisions, description writing, and a final review checklist.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [meta, skills, authoring, agent, documentation]
scope: [any]
---

# Write a Skill

Creates a new agent skill with a proper SKILL.md, optional reference files, and
utility scripts when deterministic operations are needed.

## When NOT to use this skill

- The user wants to update or refactor an existing skill. Edit the SKILL.md
  directly.
- The user wants a one-off prompt template, not a reusable skill.

## Process

1. **Gather requirements.** Ask the user:
   - What task or domain does the skill cover?
   - What specific use cases or triggers should it handle?
   - Does it need executable scripts or just instructions?
   - Any reference materials to include?

2. **Draft the skill.** Create:
   - `SKILL.md` with concise instructions (target 50-150 lines).
   - Additional reference files if content exceeds 500 lines.
   - Utility scripts if deterministic operations are needed repeatedly.

3. **Review with the user.** Present the draft and ask:
   - Does this cover your use cases?
   - Anything missing or unclear?
   - Should any section be more or less detailed?

## Skill structure

```
skill-name/
  SKILL.md           (required)
  REFERENCE.md       (if body would exceed 500 lines)
  EXAMPLES.md        (if concrete examples aid discoverability)
  scripts/           (if deterministic helper code is needed)
    helper.py
```

## Frontmatter schema

Every SKILL.md must include all seven fields or `make check` will fail:

```yaml
---
name: <slug matching directory name>
description: <one sentence, third person, starts with "Use when ...">
version: 0.1.0
owner: <github handle or name>
last_reviewed: <YYYY-MM-DD>
tags: [<3-5 relevant tags>]
scope: [<ai-backend|mcp|tm-backend|any>, ...]
---
```

## Description requirements

The description is the only thing the agent sees when deciding which skill to
load. It is surfaced in the system prompt alongside all other installed skills.

Rules:
- Max 1024 characters.
- Write in third person.
- First clause: what it does.
- Second clause: "Use when [specific triggers]."
- List two or three concrete trigger phrases the user might actually say.

Good: "Diagnose VPN connectivity when an internal service is unreachable. Use when
the user says cannot reach sonar, CI is down, or am I on the right VPN."

Bad: "Helps with network issues."

## When to add scripts

Add utility scripts when:
- The operation is deterministic (validation, formatting, calculation).
- The same code would be generated repeatedly across sessions.
- Errors need explicit handling that prose instructions cannot guarantee.

Scripts save tokens and improve reliability compared to generated code.

## When to split files

Split into separate files when:
- SKILL.md exceeds ~150 lines.
- Content has distinct domains that are rarely needed together.
- Advanced features are almost never needed for routine invocations.

## Placement convention

New skills always go to `~/.agents/skills/<name>/SKILL.md` (canonical shared
location). Agent-specific directories (`~/.claude/skills/`, `~/.codex/skills/`)
contain symlinks. Never create skills directly in agent-specific directories.

## Review checklist

Before writing the file:

- [ ] Description includes triggers ("Use when...")
- [ ] SKILL.md under 150 lines
- [ ] No time-sensitive info baked in
- [ ] Consistent terminology throughout
- [ ] "When NOT to use this skill" section present
- [ ] Frontmatter has all 7 required fields
