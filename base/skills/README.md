# Skills

This directory holds the playbook's workflow library. Each skill is ONE directory containing a `SKILL.md` file (plus optional supporting assets) that describes a reusable workflow with deterministic steps.

## What a skill is

A skill is a workflow you can hand to a coding agent and have it follow. Examples: "review a VCS PR with our conventions", "profile a new dataset before modeling", "respond to a Slack message after one verification lookup."

Different from a rule (which is an always-on constraint). Different from a subagent (which is a delegated specialist with its own context window). Different from a hook (which runs without agent involvement).

## Categories

| Category | What lives here |
|---|---|
| `engineering/` | Code-review, CI debugging, refactor patterns, performance investigations |
| `productivity/` | Slack drafts, meeting briefs, handoffs, stakeholder communication |
| `observability/` | K8s sweeps, VPN checks, dashboard interpretation, alert triage |
| `research/` | Data profiling, literature synthesis, statistical analysis, RAG evaluation, hypothesis design, notebook-to-production, agent-repo-briefing |
| `meta/` | Playbook management itself: write-a-skill, playbook-promote, playbook-retrospective, doc audits, decay checks |
| `imported/` | Catch-all for bulk-imported skills not yet recategorized. Recreated on demand by `scripts/bulk_import.py`; absent when no un-recategorized imports are pending. |

A skill belongs to ONE category; that category becomes part of its install path. Authors pick the most specific fit; "imported" is the fallback during bulk imports until the maintainer recategorizes.

## Schema (per ADR-0001)

Every skill has frontmatter:

```yaml
---
name: data-profiling                    # required; matches the directory name
description: Use when ...               # required; one sentence, starts with the trigger condition; HARD LIMIT 1024 chars (Codex rejects longer)
version: 1.0.0                          # required; per-skill semver
owner: research-team                    # required; OWNERS.md alias or individual handle
last_reviewed: 2026-05-24               # required; YYYY-MM-DD; decay-tracked
tags: [research, data, exploration]     # optional
scope: research                         # optional; broad category
---

# Skill title
Plain-language opener (one paragraph) for what this skill does for the user.

## When to use
Concrete trigger phrases or contexts.

## When NOT to use
Anti-triggers. Critical for preventing skills from misfiring.

## Workflow
Step 1 ... Step 2 ... Step 3 ...

## Worked example
A concrete walkthrough on a realistic-looking input.

## Output
What the user / next agent should see when the skill finishes.
```

## How the installer materializes skills

| Adapter | Output path |
|---|---|
| `claude_code` | `~/.claude/skills/<name>/SKILL.md` (category flattened) |
| `codex` | `~/.agents/skills/<name>/SKILL.md` (cross-tool USER skill root per OpenAI docs) |
| `cursor` | `~/.cursor/skills/<name>/SKILL.md` (and project dup if `--target`) |
| `windsurf` | `<target>/.windsurf/skills/<name>/SKILL.md` |
| `pi` | `~/.pi/agent/skills/<name>/SKILL.md` |
| `claude_code` (skill content) | Same as above |
| Tier 3 agents | Skill content not distributed; AGENTS.md only |

The full bag of skills lands in EVERY user-level adapter, regardless of category. Categories are organizational only, not selection-time filters (profiles are the filtering surface, per `profiles/README.md`).

## Quick path: adding a new skill

```bash
make new SKILL=my-workflow CATEGORY=engineering
# Scaffolds skills/engineering/my-workflow/SKILL.md with frontmatter pre-filled.
```

Edit the file, fill in the workflow, run `make check`, commit, PR.

For the slow path (capture from a real session) see `CONTRIBUTING.md` and ADR-0008 (three-layer capture system).

## Decay prevention

Per `scripts/decay_check.py`:
- `last_reviewed` 60-90 days old: notice band (informational; surfaces in `make check`)
- `last_reviewed` 90-180 days old: warning (`make check` flags but does not block)
- `last_reviewed` >180 days old: BLOCKING (`make check` fails, refuses install)

The skill's `owner` is responsible for refreshing the date when the skill is re-verified, OR removing the skill when it no longer applies.

## Quality bar (per CONTRIBUTING.md)

A skill should answer YES to all four:

1. **Does it repeat?** If you have only done this workflow once, wait. Repetition justifies packaging.
2. **Is it not already covered?** Search `skills/` and `rules/` before adding. Check `docs/research/inspirations.md` for what external libraries cover.
3. **Is the description specific?** "Use when the user says X" beats "useful for Y." Vague descriptions waste agent context.
4. **Is the owner committed to upkeep?** Owners are responsible for `last_reviewed` staying current. Do not add a skill you cannot maintain.

## References

- ADR-0001: SKILL.md format and decay discipline
- ADR-0008: three-layer capture system (mid-session quick capture, end-of-session retrospective, periodic cross-session audit)
- `scripts/new_skill.py` for the scaffold command
- `scripts/promote_skill.py` for the draft-to-merged graduation flow
