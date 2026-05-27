---
name: playbook-new-skill
description: Scaffold a new skill in the playbook with frontmatter pre-filled, walking the user through category, name, and description before running make new.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [scaffold, skills, authoring, playbook]
---

# Scaffold a new skill in the playbook

When the user wants to start authoring a new skill in the coding-agents-playbook, this command walks them through the three decisions that have to be made before scaffolding (category, name, description), runs `make new`, edits the placeholder description in the generated file, then reminds the user what they still need to fill in.

## When to use

- The user just typed `/playbook-new-skill` and wants to add a fresh skill.
- A retrospective or promotion produced a skill the user wants to author directly (skipping the proposal drafting).
- The user identified a recurring workflow during the session and is ready to package it.

## When NOT to use

- The user wants to edit an existing skill (open the SKILL.md directly).
- The user has a draft in `~/.playbook-proposals/` (use `/playbook-promote <slug>` instead, since promotion preserves the draft as evidence).
- The user wants a one-off prompt template, not a reusable skill (write to `prompts/` instead).
- The pattern was observed only once. Recommend the user wait for it to recur.

## Your job

You are the agent driving the scaffold. Ask three questions, run one command, edit one field, then hand off the body authoring to the user.

## Workflow

1. **Ask for the category.** Present the four valid options with one-line cues:
   - `engineering`: code workflows (review, refactor, debug, ship).
   - `productivity`: task and project workflows (planning, handoff, summarizing).
   - `observability`: monitoring, alerts, triage, post-incident.
   - `meta`: skills about the playbook itself (authoring, audit, promotion).

   Recommend a category based on what the user describes the skill doing. Wait for the user to confirm.

2. **Ask for the name.** Constraints:
   - Kebab-case slug, no spaces, no underscores.
   - No `team` prefix in the filename.
   - No ticket IDs (`R8-*`, `MATCH-*`).
   - Specific over generic ("code-review" beats "pr-review").

   Wait for the user to confirm.

3. **Ask for the one-sentence description.** Constraints:
   - Starts with "Use when ..." (third-person, agent-readable).
   - Names the trigger condition or user phrase that should fire this skill.
   - Max 1024 characters; aim for one to two sentences.

   Good: "Use when the user pastes a VCS PR URL or asks for a review of a VCS PR."
   Bad: "Helps with PR reviews."

   Wait for the user to confirm.

4. **Run the scaffold.** From the playbook root:
   ```bash
   make new SKILL=<name> CATEGORY=<category>
   ```
   This invokes `python3 scripts/new_skill.py --name <name> --category <category>` and creates `skills/<category>/<name>/SKILL.md` with frontmatter pre-filled.

5. **Edit the description.** Open the file and replace the placeholder description (`Use when ... (one sentence, third-person, starts with the trigger condition).`) with the description the user confirmed in step 3. Leave the body skeleton (Steps, Output shape, When NOT to use this skill) for the user to fill.

6. **Validate.** Run:
   ```bash
   make check
   ```
   If frontmatter lint fails, fix the missing field (likely owner if `$USER` was unset). If the em-dash check fails, fix it inline.

7. **Hand off to the user.** Tell them:
   - Path of the scaffolded SKILL.md.
   - What they still need to fill: Steps (procedural, ordered), Output shape (what the skill produces), When NOT to use (out-of-scope cases).
   - The body target length: 50 to 150 lines. Shorter means the skill is too simple; longer means it should be split.
   - Next: edit the body, then `make check` again, then commit on a feature branch and open a PR.

## Output

The user sees:

- The category, name, and description they chose.
- The path of the new SKILL.md.
- A clean `make check` output.
- A list of body sections that still need their content.
- The reminder: no em-dashes, no ticket IDs, no `team` prefix, description starts with "Use when ...".

## Reference

The scaffold mechanism is in `scripts/new_skill.py`. The skill authoring discipline is in `skills/meta/write-a-skill/SKILL.md`. Frontmatter requirements live in `scripts/frontmatter_lint.py` (name, description, version, owner, last_reviewed are all required). Owner aliases live in `OWNERS.md`.
