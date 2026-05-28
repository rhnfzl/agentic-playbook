# Contributing

Anyone can contribute a skill, rule, hook, MCP config, subagent, slash command, prompt template, trajectory, or profile (the 8 content types per ADR-0044). This guide covers the how.

For the why (inspiration-repo philosophy, design rationale), see `README.md` and `docs/adr/`.

## Quick path: adding a new skill

```bash
make new SKILL=my-workflow CATEGORY=engineering
# scaffolds base/skills/engineering/my-workflow/SKILL.md with frontmatter
```

Edit the SKILL.md, fill in:

- `name:` matches the directory name
- `description:` one sentence, third-person, starts with the trigger condition ("Use when ...")
- `owner:` your GitHub handle
- `last_reviewed:` today's date in YYYY-MM-DD

Then:

```bash
make check     # validates frontmatter + the full gate suite
git add base/skills/engineering/my-workflow/
git commit -m "feat(skills): add my-workflow"
git push origin feat/add-my-workflow
# open PR via GitHub UI
```

## Quick path: adding a new rule

Create `base/rules/my-rule.md`. No frontmatter required (rules are simpler than skills). The file should be:

- 1-2 paragraphs maximum.
- Clear about what to do and what not to do.
- Concrete enough that an agent can apply it without interpretation.

The installer concatenates selected rules into per-project `AGENTS.md` files.

## Quick path: adding a new subagent

Create `base/agents/<name>.md` with YAML frontmatter + markdown body per ADR-0009:

```yaml
---
name: data-explorer
description: Use when the user asks to profile a new dataset.
model: claude-opus-4-7   # optional
tools: [bash, read, edit]  # optional (cursor + claude only)
---

# Body
Markdown body that becomes the system prompt for Cursor + Claude Code subagents,
or `developer_instructions` for Codex (TOML conversion handled by the adapter).
```

Adapters convert to native format: Cursor + Claude Code get verbatim markdown, Codex gets TOML. Windsurf, Pi, and the long-tail adapters skip subagents (no native surface).

## Quick path: adding a new slash command

Create `base/commands/<name>.md` with YAML frontmatter (`name`, `description`) + markdown body. Materialized to `~/.cursor/commands/<name>.md` and `~/.claude/commands/<name>.md`. Codex (uses skills with description-match), Pi, Windsurf, and the long-tail adapters skip.

## Quick path: adding a new prompt template

Create `base/prompts/<name>.md` with YAML frontmatter (`name`, `description`) + markdown body. Materialized to `~/.pi/agent/prompts/<name>.md` (Pi's `/name` expansion surface). Files without frontmatter are setup / onboarding docs and stay unmaterialized.

## Capture path: from a real session to a PR

The two routes above (manual scaffold + edit) work well when you already know what you want to write. When the idea came from real coding work, there's a lower-friction route via the playbook's capture system.

1. **At end of session**, invoke `/playbook-retrospective`. The skill reads the session log, searches the playbook for existing coverage, and drafts proposals into `~/.playbook-proposals/<slug>.{skill,rule,hook}.md`. Drafts are gitignored; nothing leaks out yet.

2. **Sleep on it.** Drafts that survive overnight are usually worth promoting. Drafts that do not are usually one-off anecdotes.

3. **Graduate the draft** with `/playbook-promote <slug>`. The skill:
   - Finds the playbook checkout (via `$PLAYBOOK_HOME` or common paths).
   - Reads the draft, parses its proto-frontmatter.
   - Runs a grill-me-style interview (2nd source required, "When NOT to use" required, owner confirmed).
   - Creates a feature branch `feat/playbook-add-<slug>`.
   - Scaffolds via `scripts/new_skill.py` (for skills) or writes directly (rules and hooks).
   - Runs `make check`.
   - Stops. The final commit, push, and PR are yours.

4. **Open PR** as normal.

This path applies the same quality bar as the manual one; the grill-me interview enforces the "where else have you seen this?" 2nd-source check. The benefit is reduced friction at capture time, not relaxed standards at merge time. See `docs/adr/0008-three-layer-capture-system.md` for the design.

## Quality bar

A skill / rule / hook should answer YES to all four:

1. **Does it repeat?** If you have only done this workflow once, wait. Repetition justifies packaging.
2. **Is it not already covered?** Search `base/skills/` and `base/rules/` before adding. Check `docs/research/inspirations.md` for what external libraries cover.
3. **Is the description specific?** "Use when the user says X" beats "useful for Y." Vague descriptions waste agent context.
4. **Is the owner committed to upkeep?** Owners are responsible for `last_reviewed` staying current. Don't add a skill you can't maintain.

## Review process

- All PRs go through GitHub PR review.
- A PR needs 1 reviewer approval to merge.
- Skill changes need approval from the owner OR a maintainer if the owner is unavailable.

## Decay prevention

- `make check` warns when a skill's `last_reviewed` is more than 90 days old.
- `make check` blocks when it is more than 180 days old (180 days for docs-like dirs: `docs/`, `prompts/`, `profiles/`).
- The owner is responsible for refreshing the date (either confirm it still applies, or remove the skill if it does not).

## Style

- No em dashes anywhere. Use commas, parentheses, or separate sentences.
- Plain-language product context first, technical detail second.
- New content should match the voice of existing content in its category.

## ADRs

If your contribution introduces a meaningful design decision (e.g., a new file format, a new categorization, a new tool target), add an ADR under `docs/adr/`:

```
docs/adr/NNNN-short-title.md
```

ADRs are short (under 1 page typically). Format:

```markdown
# NNNN. Short title

## Status

Accepted | Proposed | Deprecated | Superseded by NNNN

## Context

What problem we are solving, what constraints apply.

## Decision

What we decided.

## Consequences

What changes, what tradeoffs we accepted.
```

The `adr_number_unique.py` check ensures no two ADRs share the same number; run `ls docs/adr/ | sort -V | tail -5` to find the next free number before writing.

## How to suggest a skill that should exist but you cannot write yourself

Open a PR with just the SKILL.md skeleton and frontmatter, marked as `status: draft`. Comment in the PR with what you want the skill to do, examples of inputs / outputs, and any context. Another contributor can pick it up.

## Where the patterns came from

This contribution model is shaped by:

- Microsoft's code-with-engineering-playbook (PR-based, ADRs alongside artifacts).
- Block / Goose (owner accountability).
- Airbnb knowledge-repo (peer review via git).

If you change this process, also update the relevant ADR.
