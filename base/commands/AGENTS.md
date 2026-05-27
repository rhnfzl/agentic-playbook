# Slash Commands

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Slash-command authoring lane. Each file here defines one `/<command>` invokable from the chat surface. Commands are short directives wired to skills, scripts, or agent dispatches.

## What Lives Here

- `<command-name>.md` files with frontmatter (description, allowed-tools when needed).
- No skills (those are in `skills/`), no rules.
- Examples: `playbook-promote.md`, `handoff.md`, `grill-me.md`.

## Local Commands

- `make check` from repo root lints frontmatter and em-dash rule.
- Install path materializes to `~/.claude/commands/` (and per-adapter equivalents).

## Edit Rules

- One command per file. Avoid composite commands; chain skills via the skill itself.
- Names are kebab-case and start with a verb or topical noun.
- Body uses imperative voice ("Read X, then Y").

## Required Checks

- Frontmatter `description` field present.
- No em dashes (em dash rule applies project-wide).
- If the command invokes a skill, the skill exists in `skills/`.

## Required Skills

- `/playbook-promote` for graduating drafts to merged.
- `/playbook-new-skill` for scaffolding a new skill.

## Do Not

- Embed long workflows in command files. If the body grows past ~50 lines, promote to a skill.
- Reference unstable upstream commands; pin to skills you control.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a command or changing an existing trigger.
