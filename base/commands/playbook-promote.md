---
name: playbook-promote
description: Graduate a draft proposal from ~/.playbook-proposals/ into the coding-agents-playbook repo as a real skill, rule, or hook.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [promotion, scaffolding, meta, playbook]
---

# Promote a draft into the playbook

When the user wants to take a draft sitting in `~/.playbook-proposals/` and turn it into a committed skill, rule, or hook in the coding-agents-playbook repo, this command runs the promotion workflow end-to-end (everything except the final commit and push).

## When to use

- The user just typed `/playbook-promote <slug>` and expects you to graduate that draft.
- A retrospective produced a draft yesterday or earlier, and today the user wants to package it.
- The user is confident the pattern recurred (two or more examples) and is ready to commit to upkeep.

## When NOT to use

- The draft was created in the same session. Sleep on it first. Tell the user to come back tomorrow.
- The user only has one example of the pattern. Recommend waiting until it recurs.
- The user cannot articulate when this skill should NOT apply. The "When NOT to use" section is load-bearing.

## Your job

You are the agent driving the promotion. Run the workflow below in order, asking the user for input only where the script cannot answer.

## Workflow

1. **Locate the proposal.** Run:
   ```bash
   ls ~/.playbook-proposals/<slug>.*.md
   ```
   If the slug was not passed, ask the user which slug to promote and list what is in the proposals directory.

2. **Read the draft.** Open the file. Note the `proposal_type` (skill, rule, or hook) and the `category` (for skills) from the proto-frontmatter. Read the body so you understand what the draft is claiming.

3. **Run the grill interview.** Ask one question at a time. Do not auto-fill answers.

   For skill proposals, ask:
   - Where else have you seen this pattern? Require a second concrete example. If the user cannot produce one, stop and tell them to wait for the pattern to recur.
   - What is the simplest version that captures the essence? Rewrite if the draft is too elaborate.
   - When should this skill NOT apply? Required. Capture the user's answer verbatim.
   - Who is the owner? Default to an alias from OWNERS.md (`playbook-core`, `backend-team`, `ai-platform`, `research-team`) or the user's handle.
   - Which agents is this for? Default `any`.

   For rule proposals, ask:
   - Is this a behavioral constraint or a workflow? If workflow, redirect to a skill scaffold.
   - Are there exceptions? Document them in the rule body.
   - Why does this exist? One-paragraph rationale.

   For hook proposals, ask:
   - What event does this fire on? PreToolUse, PostToolUse, Stop, or Notification.
   - What is the override mechanism? Hooks should never be unconditionally enforcing.
   - What is the failure mode if the hook misfires? Block or warn.

4. **Run the promotion script.** From the playbook root:
   ```bash
   python3 scripts/promote_skill.py --slug <slug>
   ```
   The script will: find the playbook checkout, create branch `feat/playbook-add-<slug>`, scaffold the artifact (via `scripts/new_skill.py` for skills, or write rule/hook files directly with collision protection), and print the next steps. Pass `--owner <alias>` if the user specified a different owner. Pass `--no-branch` only if the user explicitly asked to skip branch creation.

5. **Merge the interview answers into the scaffold.** Open the scaffolded file the script printed. Replace the placeholder description with the one the user confirmed. Replace placeholder body steps with the real procedure. Add the "When NOT to use this skill" section using the user's verbatim answer.

6. **Validate.** Run:
   ```bash
   make check
   ```
   Fix any frontmatter, decay, or em-dash issues before continuing.

7. **Prepare the PR description.** Draft a VCS PR body in the writing-style shape:
   - Plain-language opener: what this gives the team.
   - Why now: the pattern that motivated promotion.
   - What changed: file paths added.
   - Source pointers: the proposal evidence from the draft.

8. **Stop.** Do NOT commit, push, or open the PR. Tell the user:
   - Branch name created
   - Files added or changed
   - Suggested commit message: `feat(<type>): add <slug>`
   - Final steps for the user: stage, commit, push to VCS, open the PR

## Output

The user sees:

- A summary of what the interview decided.
- The path of the scaffolded file in the playbook.
- A clean `make check` output.
- The drafted PR description ready to paste.
- A reminder that the proposal in `~/.playbook-proposals/` stays until the PR merges.

## Reference

The mechanism is implemented in `scripts/promote_skill.py`. The three-layer capture system is documented in `docs/adr/0008-three-layer-capture-system.md`. The skill body in `skills/meta/playbook-promote/SKILL.md` carries the same workflow this command invokes.
