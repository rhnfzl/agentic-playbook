---
name: playbook-promote
description: Use when ready to graduate a draft proposal from ~/.playbook-proposals/ into the coding-agents-playbook repo. Reads the draft, runs grill-me-style clarification questions (sources, scope, when-NOT-to-use, owner), then scaffolds the proper skill/rule/hook via scripts/new_skill.py, creates a feature branch, and prepares the PR description. Final commit + push is the user's job.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [promotion, scaffolding, meta]
scope: [any]
---

# Playbook Promote

Use when you have a draft in `~/.playbook-proposals/` that is ready to become a real skill, rule, or hook in the coding-agents-playbook.

This is the promotion path for the 3-layer capture system. See `docs/adr/0008-three-layer-capture-system.md`.

## When to use

- After a `/playbook-retrospective` produced a draft you have sat with for at least one more session and still feel is worth keeping.
- When promoting from draft to SKILL.md / rule.md / hook.sh and opening a PR is the natural next step.
- When you have ground the pattern in 2 or more concrete examples (one is anecdote; two is pattern).

## When NOT to use

- Do not promote on the same day the retrospective drafted it. Sleep on it first; many "useful patterns" do not survive a second look.
- Do not promote if the draft is grounded in only 1 source. Wait for the pattern to recur.
- Do not promote if you cannot articulate a clear "When NOT to use this" section. If you cannot bound the skill, it is not ready.
- Do not promote a draft you did not write yourself. The owner has to commit to upkeep.

## Procedure

1. **Locate the playbook checkout.** The promotion script searches in order:
   - `$PLAYBOOK_HOME` env var if set
   - `~/team/coding-agents-playbook/`
   - `~/coding-agents-playbook/`
   - `~/projects/coding-agents-playbook/`
   - `~/src/coding-agents-playbook/`

   Hard-fail with a helpful message if none found.

2. **Read the draft** at `${PLAYBOOK_PROPOSALS_DIR}/<slug>.{skill,rule,hook}.md`. Parse its proto-frontmatter to determine `proposal_type` and (for skills) `category`.

3. **Run the grill-me interview.** Each question is required; do not auto-fill.

   For skills:
   - "Where else have you seen this pattern?" Require a 2nd concrete example. If the user cannot produce one, abort and tell them to wait.
   - "What is the simplest version that captures the essence?" Rewrite if the draft is too elaborate.
   - "When should this skill NOT apply?" Required. This section is load-bearing; the skill is incomplete without it.
   - "Who is the owner?" Default to current `$USER`. Confirm the user is committing to upkeep.
   - "Which agent(s) is this for?" `scope:` field. Default `any`.

   For rules:
   - "Is this a behavioral constraint or a workflow?" If workflow, redirect to skill scaffold.
   - "Are there exceptions?" If yes, document them in the rule body.
   - "Why does this exist?" One-paragraph rationale.

   For hooks:
   - "What event does this fire on?" PreToolUse / PostToolUse / Stop / Notification?
   - "What is the override mechanism?" Hooks should not be unconditionally enforcing.
   - "What is the failure mode if the hook misfires?" Block vs warn?

4. **Create a feature branch** in the playbook checkout:
   ```
   git checkout -b feat/playbook-add-<slug>
   ```

5. **Scaffold the artifact** in the playbook:
   - For skills: run `scripts/new_skill.py --name <slug> --category <category> --owner <owner>`. Then merge the interview answers into the scaffolded SKILL.md, preserving the canonical frontmatter and adding the "When NOT to use this skill" section.
   - For rules: write directly to `rules/<slug>.md`. No frontmatter. 1-2 paragraphs maximum.
   - For hooks: write to `hooks/<slug>.sh`. Make executable (`chmod +x`). Include override-via-env mechanism per the existing `never-push-to-develop.sh` pattern.

6. **Run validation:**
   ```
   make check
   ```
   Fix any frontmatter / decay issues before proceeding.

7. **Produce a PR description** following CONTRIBUTING.md style: plain-language context first, technical detail second. Include the draft's source pointers as evidence.

8. **Stop.** Do NOT auto-commit, do NOT auto-push, do NOT auto-open the PR. Tell the user:
   - Branch name created
   - Files added/changed
   - Suggested commit message
   - Next steps: `git add . && git commit -m '...' && git push -u origin <branch>` then open PR in VCS

## What this skill does NOT do

- Does NOT commit or push automatically. Final review is the user's.
- Does NOT delete the draft after promotion. The user removes `~/.playbook-proposals/<slug>.*.md` manually after the PR merges.
- Does NOT open the VCS PR via API. The skill prepares everything; the user clicks "Create PR" in the VCS UI.
- Does NOT modify rules in ways that change the canonical AGENTS.md format. If a rule needs format changes, that is a separate PR.

## Helper script

Backend logic is in `scripts/promote_skill.py`. The script handles: finding the playbook checkout, parsing the draft, creating the feature branch, scaffolding via `new_skill.py`, writing rules/hooks to their final locations. The skill drives the interview; the script does the file IO.

## Configuration

- `PLAYBOOK_HOME` (default: search common paths): location of the playbook checkout.
- `PLAYBOOK_PROPOSALS_DIR` (default: `~/.playbook-proposals/`): where drafts live.
