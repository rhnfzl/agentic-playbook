# Contributing

Anyone on the team team can contribute a skill, rule, hook, MCP config, subagent, slash command, prompt template, or profile (7 content types as of v0.2). This guide covers the how.

For the why (inspiration-repo philosophy, design rationale), see `README.md` and `docs/adr/`.

## Quick path: adding a new skill

```bash
make new SKILL=my-workflow CATEGORY=engineering
# scaffolds base/skills/engineering/my-workflow/SKILL.md with frontmatter
```

Edit the SKILL.md, fill in:

- `name:` matches the directory name
- `description:` one sentence, third-person, starts with the trigger condition ("Use when ...")
- `owner:` your VCS handle
- `last_reviewed:` today's date in YYYY-MM-DD

Then:

```bash
make check     # validates frontmatter
git add base/skills/engineering/my-workflow/
git commit -m "feat(skills): add my-workflow"
git push origin feat/add-my-workflow
# open PR
```

## Quick path: adding a new rule

Create `base/rules/my-rule.md` (or `overlays/team/rules/my-rule.md` if the rule is team-specific; see "Choosing base vs overlays/team" below). No frontmatter needed (rules are simpler than skills). The file should be:

- 1-2 paragraphs maximum
- Clear about what to do and what not to do
- Concrete enough that an agent can apply it without interpretation

The installer will concatenate selected rules into per-subproject AGENTS.md files.

## Quick path: adding a new subagent (v0.2)

Create `base/agents/<name>.md` (or `overlays/team/agents/<name>.md` for team-specific) with YAML frontmatter + markdown body per ADR-0009:

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

Adapters convert to native format: Cursor + Claude Code get verbatim markdown, Codex gets TOML. Windsurf, Pi, Antigravity skip subagents (no native surface).

## Quick path: adding a new slash command (v0.2)

Create `base/commands/<name>.md` with YAML frontmatter (`name`, `description`) + markdown body. Materialized to `~/.cursor/commands/<name>.md` and `~/.claude/commands/<name>.md`. Codex (uses skills with description-match), Pi, Windsurf, Antigravity all skip (no native commands surface).

## Quick path: adding a new prompt template (v0.2)

Create `base/prompts/<name>.md` (or `overlays/team/prompts/<name>.md` for team-specific) with YAML frontmatter (`name`, `description`) + markdown body. Materialized to `~/.pi/agent/prompts/<name>.md` (Pi's `/name` expansion surface). Files without frontmatter are setup/onboarding docs and stay unmaterialized.

## Capture path: from a real session to a PR

The two routes above (manual scaffold + edit) work well when you already know what you want to write. When the idea came from real coding work, there is a lower-friction route via the playbook's capture system.

1. **At end of session**, invoke `/playbook-retrospective`. The skill reads the session log, searches the playbook for existing coverage, and drafts proposals into `~/.playbook-proposals/<slug>.{skill,rule,hook}.md`. Drafts are gitignored; nothing leaks out yet.

2. **Sleep on it.** Drafts that survive overnight are usually worth promoting. Drafts that do not are usually one-off anecdotes.

3. **Graduate the draft** with `/playbook-promote <slug>`. The skill:
   - Finds the playbook checkout (via `$PLAYBOOK_HOME` or common paths)
   - Reads the draft, parses its proto-frontmatter
   - Runs a grill-me-style interview (2nd source required, "When NOT to use" required, owner confirmed)
   - Creates a feature branch `feat/playbook-add-<slug>`
   - Scaffolds via `scripts/new_skill.py` (for skills) or writes directly (rules and hooks)
   - Runs `make check`
   - Stops. The final commit, push, and PR are yours

4. **Open PR** as normal. The reviewer pool is the same (rehan, the AI Backend collaborator initially; domain reviewers as the system grows).

This path applies the same quality bar as the manual one, the grill-me interview enforces the "where else have you seen this?" 2nd-source check. The benefit is reduced friction at capture time, not relaxed standards at merge time. See `docs/adr/0008-three-layer-capture-system.md` for the design.

## Quality bar

A skill/rule should answer YES to all four:

1. **Does it repeat?** If you have only done this workflow once, wait. Repetition justifies packaging.
2. **Is it not already covered?** Search `base/skills/`, `overlays/team/skills/`, `base/rules/`, and `overlays/team/rules/` before adding. Check `docs/research/inspirations.md` for what external libraries cover.
3. **Is the description specific?** "Use when the user says X" beats "useful for Y." Vague descriptions waste agent context.
4. **Is the owner committed to upkeep?** Owners are responsible for `last_reviewed` staying current. Do not add a skill you cannot maintain.

## Choosing base vs overlays/team (ADR-0040)

Every new content file lands in either `base/<type>/` (generic, vendor-neutral) or `overlays/team/<type>/` (team-specific). Use this three-bucket policy:

1. **STRICT team** -> `overlays/team/<type>/`. The file IS an team-only artifact: skills tied to internal services (error-tracking, CI, code-quality, internal Kubernetes), rules naming team ticket projects (R8/MATCH), agents that reference team-internal stack.

2. **GENERIC with team examples** -> `base/<type>/`. The file is a universal rule or skill that uses team as an illustrative example (e.g. `base/rules/never-push-to-develop.md` mentions VCS as a concrete trigger context; the rule itself is universal). The `scope_boundary.py` check enforces base/ stays clean of strong team markers (R8-/MATCH- ticket IDs, team, internal-host, VCS.org) except for files explicitly allowlisted with rationale.

3. **HYBRID** -> split if practical (extract the team section into `overlays/team/<type>/`); otherwise classify by PRIMARY AUDIENCE. Decision rule: "if a base-only user gets value from this file, base; if value is only realized with team context, overlay."

Run `make check` after committing; the scope-boundary check fails if base/ gains a hit without an allowlist entry in `scripts/checks/scope_boundary_allowlist.toml`. Allowlist additions must include a non-empty rationale.

## Review process

- All PRs go through VCS PR review.
- Initial reviewers: Rehan, the AI Backend collaborator.
- A PR needs 1 reviewer approval to merge.
- Skill changes need approval from the owner OR a reviewer if the owner is unavailable.

## Decay prevention

- `make check` warns when a skill's `last_reviewed` is greater than 90 days old.
- `make check` blocks when it is greater than 180 days old.
- The owner is responsible for refreshing the date (either confirm it still applies, or remove the skill if it does not).

## Style

- No em dashes anywhere. Use commas, parentheses, or separate sentences.
- No team prefix in file names. VCS workspace already prefixes ownership.
- Plain-language product context first, technical detail second.

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

## How to suggest a skill that should exist but you cannot write yourself

Open a PR with just the SKILL.md skeleton and frontmatter, marked as `status: draft`. Comment in the PR with what you want the skill to do, examples of inputs/outputs, and any context. Another contributor can pick it up.

## Where the patterns came from

This contribution model is shaped by:

- Microsoft's code-with-engineering-playbook (PR-based, ADRs alongside artifacts)
- Block/Goose (owner accountability)
- Airbnb knowledge-repo (peer review via git)

If you change this process, also update the relevant ADR.
