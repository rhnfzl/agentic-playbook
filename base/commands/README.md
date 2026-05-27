# Commands

Slash commands the user types directly in the chat surface to trigger a specific behavior. Each `<name>.md` here defines one `/<name>` invokable from Cursor, Claude Code, and Codex. The 5th content type the playbook ships (per ADR-0010), sitting alongside skills (workflows), rules (constraints), hooks (lifecycle scripts), and prompts (templates).

## What a command is

A command is a short directive that the agent runs when the user types `/<name>` (or selects it from the command palette). Different from a skill (which the agent picks up when relevant) and a hook (which fires without agent involvement). Commands are user-initiated and explicit.

The body of a command is usually a few sentences plus a workflow checklist that the agent follows. Commands typically wire into one or more skills, scripts, or subagent dispatches rather than embedding the whole workflow inline.

## What ships in this directory

| Command | What it does |
|---|---|
| `playbook-doctor.md` | `make doctor` interpretation; detection map + layer-3 verify guidance. |
| `playbook-check.md` | Walks `make check` output and flags any drift. |
| `playbook-new-skill.md` | Scaffolds a new skill via `make new`. |
| `playbook-promote.md` | Graduates a draft skill to merged. |
| `playbook-retrospective.md` | Captures a session's learnings into the skill base. |
| `grill-me.md` | Interactive interview-style review (one question at a time). |
| `handoff.md` | Writes a handoff doc for the next coding agent. |
| `human-html.md` | Scaffolds + validates HTML artifacts under `docs/human-html/`. |

The exact list ships in this directory; `ls commands/*.md` is the source of truth.

## Schema

Frontmatter (one block at the top):

```yaml
---
name: my-command
description: One-sentence trigger condition; starts with "Use when ..."
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-25
allowed-tools: [Bash, Read, Edit]  # optional; restricts what the agent can do
tags: [doctor, install, playbook]  # optional
---
```

Body conventions:
- Imperative voice ("Read X, then Y").
- A `## Workflow` section with numbered steps.
- A `## When to use` and `## When NOT to use` pair to prevent misfires.
- A `## Output` section that names what the user should see when the command finishes.

## How the installer materializes commands

| Adapter | Output path |
|---|---|
| `claude_code` | `~/.claude/commands/<name>.md` |
| `cursor` | `~/.cursor/commands/<name>.md` |
| `codex` | not materialized; Codex slash commands are agent-defined, not file-driven |

Project-level commands at `<target>/.claude/commands/<name>.md` are written when `--target` is set, so a single project can ship its own commands alongside the global set.

## How to add a new command

1. Scaffold: nothing automated yet; copy an existing command file as a template.
2. Frontmatter: name matches the filename (without `.md`); `description` opens with "Use when ..." to help the agent decide when to invoke.
3. Body: name the inputs, name the outputs, list the workflow steps in order.
4. Run `make check` (frontmatter + em-dash lint).
5. Open a PR.

## Quality bar

- One command per file. Composite commands belong in a skill that orchestrates several steps.
- If the body grows past ~50 lines, promote the workflow to `skills/` and let the command be a thin wrapper.
- A command must NAME ITS TRIGGER. Vague descriptions waste agent context (and waste the user's keystroke).

## References

- ADR-0010 (commands + prompts as 5th and 6th content types).
- `commands/AGENTS.md` (concise edit rules for in-flight authoring).
- `skills/README.md` (when to write a skill instead of a command).
- [docs.cursor.com/context/commands](https://docs.cursor.com/context/commands) (Cursor slash commands)
- [code.claude.com/docs/en/commands](https://code.claude.com/docs/en/commands) (Claude Code slash commands)
