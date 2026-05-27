# 0004. Drop the team prefix from file names

## Status
Accepted (2026-05-24)

## Context

Many existing personal skills in `~/.agents/skills/` carry an `team-` prefix (e.g., `team-agentic-scenario-triage`, `team-post-iter-review`). When lifting them into a shared team repo, we faced the question: keep the prefix, or drop it?

## Decision

Drop the team prefix everywhere. File names are `agentic-scenario-triage`, `post-iter-review`, etc.

## Why

The VCS workspace prefixes ownership: `team/coding-agents-playbook/...`. Every file in the repo is implicitly team-owned. Repeating "team-" on every filename adds noise without information.

This is consistent with mattpocock's pattern: his repo is `mattpocock/skills`, not `mattpocock/matt-skills`. The slugs are `grill-me`, `diagnose`, `tdd`, not `matt-grill-me`, `matt-diagnose`, `matt-tdd`.

## Consequences

- Skill slugs and rule names are shorter and more readable.
- Migration cost: existing `team-*` skill names become un-prefixed names. Users who reference them by old name break.
- The playbook's transferability framing ("clone this and adapt it for your team") is improved: another team can fork without the team prefix screaming at them in every file.

## Exception

Brand references in skill BODIES (not names) are fine: "team Public API", "team VPN", "team MCP". The rule is specifically about file/directory names.

## When to use the prefix

In skill bodies and documentation, refer to specific team assets by their proper names (e.g., "the team Public API at app.team.com"). Drop the prefix only from filenames and directory names where the workspace context already makes ownership clear.
