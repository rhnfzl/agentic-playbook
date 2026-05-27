# Agents Contract for the Coding Agents Playbook Repo

Owner: Rehan
last_reviewed: 2026-05-25

This file is the per-repo AGENTS.md for the playbook itself. It tells any coding agent working in this repo what conventions apply.

It is also a deliberate example: a per-subproject AGENTS.md is the architectural pattern the playbook recommends. This file is what one of those looks like in practice.

## Repo purpose

A tool-agnostic, team-shared system for coding agents. See `README.md` for the long form.

## Editing conventions

- **No em dashes.** Use commas, parentheses, or separate sentences.
- **No team prefix in file names.** The VCS workspace already prefixes ownership. Files are `VCS-pr-review.md`, not `team-VCS-pr-review.md`.
- **VCS not GitHub.** When referencing version control workflows, default to VCS conventions (the team uses VCS).
- **Plain-language product context first.** When writing any explainer, lead with what something does for the user, then the technical detail.

## Skill authoring

- Every skill is one directory under `skills/<category>/<skill-name>/`.
- Each skill has a `SKILL.md` with frontmatter (`name`, `description`, `version`, `owner`, `last_reviewed`, `tags`, `scope`).
- See `skills/productivity/grill-me/SKILL.md` for a reference example.
- Use `make new SKILL=<name>` to scaffold a new skill.

## Rule authoring

- Each rule is one markdown file in `rules/`.
- A rule is a behavioral constraint, not a workflow. If it is a sequence of steps, it is a skill, not a rule.
- The installer concatenates selected rules into the per-subproject AGENTS.md it materializes.

## Pre-commit discipline

Before committing in this repo:

1. `make check` (frontmatter lint + decay warnings) must pass.
2. If any skill or rule was edited, update its `last_reviewed:` date to today.
3. If a design decision changed, add an ADR under `docs/adr/`.

## Reviewer pool

Initial reviewers: Rehan, the AI Backend collaborator. As the system grows, domain reviewers (frontend lead for frontend skills, etc.) will be added.

## When you (the coding agent) are unsure

If you are an agent reading this and you are not sure whether to act:

- For a skill that has a clear procedure: follow it.
- For a rule that conflicts with what the user is asking: surface the conflict to the user before proceeding.
- For an architecture decision not covered: read `docs/adr/` and `docs/research/` before guessing.
- If you find a documented failure mode in `docs/research/failure-modes.md` that applies: prefer the documented mitigation.

## Inspirations

This repo is heavily inspired by:

- mattpocock/skills (skill format, category split)
- Block/Goose (rules vs recipes separation)
- Stripe Minions (directory-scoped rules)
- Microsoft code-with-engineering-playbook (rationale IS the value)

Full lineage in `docs/research/inspirations.md` (to be written in week 3).
