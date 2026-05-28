# Agents Contract for agentic-playbook

This file is the per-repo `AGENTS.md` for the playbook itself. Any coding agent working in this repo reads it on entry and follows the conventions below. The same conventions land in projects that install the playbook via `make install` (the installer concatenates rules from `base/rules/` into the project's own `AGENTS.md`).

Owner: rehan
Last reviewed: 2026-05-28

## Scope: this is a personal portfolio project

This repo is an independent personal project. It exists for portfolio + experimentation purposes. It is NOT a fork, mirror, or downstream of any work-related codebase, and any incidental similarities to work patterns are coincidental.

Work-related rules that ship in `~/AGENTS.md` (employer-specific ticket trackers, internal services, request-chain architectures, vendor inventories, branch policies, etc.) DO NOT apply here. Do not import work-context assumptions when reasoning about this repo:

- Do not assume a specific issue tracker, ticket prefix, or label policy.
- Do not assume a specific VCS host beyond what this repo's `.git/config` and CI files state.
- Do not assume a specific internal API, gateway, or backend exists.
- Do not propose work-internal-tool integrations unless the user explicitly asks for them.
- Do not pull patterns from work memory or work code into this repo "by analogy" without an explicit request.

If a rule, pattern, or piece of context only makes sense in a work setting, treat it as out-of-scope here. Surface the boundary explicitly to the user instead of silently applying it.

## Repo purpose

A tool-agnostic, shareable system for working with coding agents. See `README.md` for the long form.

## Editing conventions

- **No em dashes.** Use commas, parentheses, or separate sentences. The `check_em_dashes.py` gate enforces this.
- **Plain-language product context first.** When writing any explainer, lead with what something does for the user, then the technical detail.
- **Match the existing voice.** This repo is deliberately written in clear, terse prose. New content should read at the same register.

## Skill authoring

- Every skill is one directory under `base/skills/<category>/<skill-name>/`.
- Each skill has a `SKILL.md` with frontmatter (`name`, `description`, `version`, `owner`, `last_reviewed`, `tags`, `scope`).
- See `base/skills/productivity/grill-me/SKILL.md` for a reference example.
- Use `make new SKILL=<name>` to scaffold a new skill.
- See `CONTRIBUTING.md` for the full workflow.

## Rule authoring

- Each rule is one markdown file in `base/rules/`.
- A rule is a behavioral constraint, not a workflow. If it is a sequence of steps, it is a skill, not a rule.
- The installer concatenates selected rules into the per-project `AGENTS.md` it materializes.
- Rules should be portable (no workspace-specific examples in the body).

## Hook authoring

- Each hook is one shell script in `base/hooks/`.
- The script must respond to the lifecycle events documented in `base/hooks/README.md`.
- Test hooks locally before committing (`bash -n hooks/my-hook.sh` for syntax; manual invocation for behavior).

## Pre-commit discipline

Before committing in this repo:

1. `make check` must pass (frontmatter, decay, em-dashes, content tiering, ADR uniqueness).
2. If any skill / rule / hook was edited, update its `last_reviewed:` date to today.
3. If a design decision changed, add an ADR under `docs/adr/` with the next free number.

## Reviewer pool

Maintainer reviews are by Rehan. As the repo grows, content-area reviewers can be added (frontend lead for frontend skills, etc.). PRs are welcome; expect a turn-around within a few days.

## When you (the coding agent) are unsure

If you are an agent reading this and you are not sure whether to act:

- For a skill that has a clear procedure: follow it.
- For a rule that conflicts with what the user is asking: surface the conflict to the user before proceeding.
- For an architecture decision not covered: read `docs/adr/` and `docs/research/` before guessing.
- For anything destructive (rm, force-push, schema migration): always confirm with the user first.

## Inspirations

This repo is heavily inspired by:

- mattpocock/skills (skill format, category split)
- Block/Goose (rules vs recipes separation)
- Stripe Minions (directory-scoped rules)
- Microsoft code-with-engineering-playbook (rationale IS the value)

Full lineage in `docs/research/inspirations.md`.
