---
name: playbook-retrospective
description: Use at the end of a coding session to capture playbook-worthy learnings before they fade. Analyzes the current Claude Code or Codex session log, extracts patterns (recurring corrections, new techniques, repeatable workflows), and drafts proposal markdown files in ~/.playbook-proposals/ that can later be promoted into the coding-agents-playbook repo. Manual-trigger only.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [retrospective, learning, capture, meta]
scope: [any]
---

# Playbook Retrospective

Use at the end of a coding session to capture playbook-worthy learnings before they fade. Manual-trigger only, never fires automatically. Output goes to `~/.playbook-proposals/` as gitignored drafts; promote to the playbook later via `/playbook-promote <slug>`.

This is Layer 2 of the three-layer capture system. See `docs/adr/0008-three-layer-capture-system.md` for the full design.

## When to use

- End of a session where you noticed a recurring pattern, fix recipe, or workflow worth packaging.
- After resolving a bug or process problem where the solution generalizes.
- When you said "I should remember this" or "this is repeatable" during the session.
- After a meeting transcript or code review surfaced a convention the team should encode.

## When NOT to use

- Mid-session. You're in flow; do not break it. Learning happens at reflection time.
- After a quick lookup or trivial session. Nothing to capture; skip.
- For one-off project-specific decisions. Those belong in the project's notes, not the playbook.
- On the same draft twice. If `~/.playbook-proposals/<slug>.skill.md` already exists, you are duplicating.

## Procedure

1. **Locate the current session JSONL.** Claude Code stores it at:
   ```
   ~/.claude/projects/<project-slug>/<session-id>.jsonl
   ```
   where `<project-slug>` is the absolute cwd with `/` replaced by `-`. Codex stores its session under `~/.codex/sessions/`. Read the JSONL and extract: user edits, bash commands, the user's last few prompts, any corrections (the user said "no, that's wrong" or "actually do X").

2. **Search the playbook for existing coverage.** Before drafting anything new, grep:
   - `skills/*/*/SKILL.md` for `description:` lines
   - `rules/*.md` for headings
   - `hooks/*.sh` for filenames

   If a candidate learning is already covered by an existing artifact, skip it. The retrospective should reduce duplication, not produce it.

3. **Classify remaining candidates** into one of three buckets:
   - **Skill candidate**: a workflow with 3+ steps that could repeat. Triggered by phrases like "step 1... step 2... step 3..." or sequences of similar tool calls.
   - **Rule candidate**: a behavioral constraint ("always X" / "never Y"). Triggered by the user correcting the agent or by a recurring style/convention point.
   - **Hook candidate**: enforcement that should fire automatically. Triggered by the user manually checking the same thing every session (lint, sonar, push guard) that could be automated.

4. **Draft a proposal** for each remaining candidate in `~/.playbook-proposals/` (or `$PLAYBOOK_PROPOSALS_DIR` if set). One file per candidate. Naming:
   - `<slug>.skill.md` for skill candidates
   - `<slug>.rule.md` for rule candidates
   - `<slug>.hook.md` for hook candidates

5. **Use the proposal format** defined below. Frontmatter is proto-frontmatter; promotion will refine it.

6. **Tell the user**: where drafts landed, what's in each (one-line summary), and the next step (`/playbook-promote <slug>` when ready). Do NOT auto-promote. Drafts should sit overnight at minimum.

## Proposal format (proto-frontmatter)

```
---
proposal_type: skill | rule | hook
slug: <kebab-case>
category: engineering | productivity | observability | meta   # skills only
sources:
  - <path>:<line>           # concrete evidence pointer
  - session <session-id> turn <n>
captured_at: YYYY-MM-DD
status: draft
---

# <Title>

<draft body. Same shape as a real SKILL.md / rule.md / hook.sh, but rough.
The promotion command will refine, add the "When NOT to use" section,
ground in additional sources, and run frontmatter lint.>
```

## What NOT to draft

- Anything that's already covered by an existing skill or rule. Search first.
- Anything purely project-specific (e.g., "remember [ticket] lookup pattern"). Those belong in commit notes.
- Anything that's a workaround for a bug that will be fixed. Skills capture durable workflows, not bandaids.
- Anything observed only once. Repetition is required (this skill should ask itself: "where else have I seen this?" before drafting).

## Configuration

- `PLAYBOOK_PROPOSALS_DIR` (default: `~/.playbook-proposals/`): where drafts go. Decoupled from the playbook checkout so the same drafts work across any working directory.
- `PLAYBOOK_HOME`: not used by this skill directly; the promotion command uses it.

## Helper script

Backend file IO is in `scripts/retrospective.py` in the playbook. The skill calls it for: locating the session JSONL, reading messages, writing proposal files. The LLM (the agent running this skill) does the classification.

## How this fits the 3-layer capture system

- **L1 (mid-session capture)**: not implemented for v0.1. Mid-session capture breaks flow and learning has not yet evolved.
- **L2 (this skill)**: manual end-of-session retrospective, drafts proposals.
- **L3 (`/skill-progression-map`)**: existing weekly Codex automation acts as a safety net.

Drafts from L2 are private (`~/.playbook-proposals/`, gitignored) until promoted via `/playbook-promote <slug>`.
