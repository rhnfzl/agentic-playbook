# Subagents

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Subagent definition files. Each markdown file here defines one specialized agent that the parent agent can delegate work to (read-only investigators, reviewers, validators, auditors).

## What Lives Here

- `<agent-name>.md` files with frontmatter defining tools, model, and persona.
- `README.md` documents the subagent inventory and selection guidance.
- No skills, no rules, no scripts. Only agent definitions.

## Local Commands

- `make check` from repo root validates frontmatter via `frontmatter_lint.py`.
- No agent-specific commands; install path lands these in `~/.claude/agents/`.

## Edit Rules

- Edit individual `<agent>.md` files directly.
- Update `README.md` when adding or removing an agent.
- Do not edit installer materialization paths here; that belongs in `scripts/adapters/`.

## Required Checks

- Frontmatter present and valid.
- Description matches the trigger condition; agents activate from descriptions.
- Tool allowlist is minimal (least privilege).

## Required Skills

- None mandatory. When promoting a draft agent, use `/playbook-promote` to grade it.

## Do Not

- Bundle scripts into agent files. If an agent needs code, the code lives in `scripts/` and the agent calls it.
- Hardcode team-internal paths in agent definitions intended for general use.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` whenever an agent's tool allowlist or trigger description changes.
