---
name: playbook-retrospective
description: End-of-session sweep that audits the current session and drafts skill, rule, or hook proposals into ~/.playbook-proposals/ for later promotion.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [retrospective, learning, capture, meta, playbook]
---

# Capture playbook-worthy learnings from this session

When the user wants to look back at the session that just happened and pull out anything worth packaging into a reusable skill, rule, or hook, this command runs the retrospective workflow. It is manual-trigger only (per ADR-0008, Layer 2 of the three-layer capture system). The output is gitignored drafts in `~/.playbook-proposals/`. Drafts sit for at least overnight before promotion.

## When to use

- The user typed `/playbook-retrospective` at the end of a meaningful session.
- The session involved a recurring fix, a new technique, or a workflow the user noticed themselves doing twice.
- The user said something like "I should remember this" or "this is repeatable" during the session.
- A meeting transcript or code review surfaced a team convention worth encoding.

## When NOT to use

- Mid-session. Learning evolves; a pattern noticed mid-flow is often wrong.
- After a trivial lookup session with no recurring patterns.
- When the user just wants a summary or handoff (use `/handoff` instead).
- When a similar draft already exists at `~/.playbook-proposals/<slug>.skill.md`. Duplicating proposals defeats the purpose.

## Your job

You are the agent driving the retrospective. Read the current session, search the existing playbook for coverage, then call back into `scripts/retrospective.py` to write any new proposals.

## Workflow

1. **Locate the session JSONL.** Run:
   ```bash
   python3 scripts/retrospective.py --session-id <id> --cwd "$(pwd)"
   ```
   If the user did not pass a session id, ask. Claude Code stores sessions at `~/.claude/projects/<cwd-slug>/<session-id>.jsonl` where `<cwd-slug>` is the absolute cwd with `/` replaced by `-`. Codex stores under `~/.codex/sessions/YYYY/MM/DD/`. The script handles both.

2. **Read the session messages.** Walk through user prompts, agent edits, bash commands, and any corrections. Pay attention to:
   - Phrases like "no, that's wrong" or "actually do X" (correction signals).
   - Multi-step workflows the agent executed (skill candidates).
   - The user repeating the same instruction across turns (rule candidates).
   - Manual checks the user ran every time (hook candidates).

3. **Search the existing playbook for coverage.** Before drafting anything new:
   ```bash
   grep -ri "description:" skills/*/*/SKILL.md
   ls rules/ hooks/
   ```
   If a candidate is already covered by an existing artifact, skip it. The retrospective reduces duplication, not produces it.

4. **Classify remaining candidates** into one of three buckets:
   - **Skill**: a workflow with three or more steps that could repeat. Lives at `skills/<category>/<slug>/SKILL.md`.
   - **Rule**: a behavioral constraint ("always X", "never Y"). Lives at `rules/<slug>.md`.
   - **Hook**: enforcement that should fire automatically. Lives at `hooks/<slug>.sh`.

5. **Draft each candidate.** Import the helper and call it once per candidate:
   ```python
   from retrospective import write_proposal
   write_proposal(
       slug="my-pattern",
       proposal_type="skill",
       body="<draft body>",
       category="engineering",
       sources=["session <id> turn <n>", "<file>:<line>"],
   )
   ```
   Or invoke via shell using a small inline script. One proposal per candidate. Naming is:
   - `<slug>.skill.md` for skills
   - `<slug>.rule.md` for rules
   - `<slug>.hook.md` for hooks

6. **Report to the user.** Tell them:
   - Where drafts landed (the path).
   - A one-line summary per candidate.
   - The next step (`/playbook-promote <slug>` when ready, but only after sleeping on it).

## Output

The user sees:

- A list of zero to three drafts written, with their slugs and one-line summaries.
- The path to each file in `~/.playbook-proposals/`.
- A reminder: do NOT promote on the same day. Let the pattern settle. Promotion is the gate.

## What NOT to draft

- Anything already covered by an existing skill or rule. Search first.
- Anything purely project-specific (a single ticket number, a one-off fix). Those go in commit notes.
- Anything observed only once. Repetition is required; ask yourself "where else have I seen this?" before drafting.
- Workarounds for a bug that will be fixed. Skills capture durable workflows, not bandaids.

## Configuration

- `PLAYBOOK_PROPOSALS_DIR` (default `~/.playbook-proposals/`): where drafts go.

## Reference

ADR-0008 (`docs/adr/0008-three-layer-capture-system.md`) is the canonical design for the three-layer capture system. This command is Layer 2 (session-end). Layer 3 is the periodic `/skill-progression-map` automation. Layer 1 (mid-session capture) is intentionally not implemented.

The file-IO backend is `scripts/retrospective.py`. The skill body in `skills/meta/playbook-retrospective/SKILL.md` carries the same workflow.
