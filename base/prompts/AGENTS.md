# Prompts

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Reusable prompt templates per ADR-0010. Prompts are deterministic content the user invokes; they differ from commands (which dispatch to agents) and skills (which orchestrate workflows).

## What Lives Here

- `<prompt-name>.md` files: bootstrap-your-playbook, clarify-then-deliver, discover-repeatable-workflows, onboard-a-new-teammate, etc.
- `README.md` documents the prompt format and adapter materialization.

## Local Commands

- `make check` runs em-dash check and freshness over prompt files.
- The installer materializes prompts to the adapter's prompt directory (e.g. `~/.claude/prompts/` on adapters that support them).

## Edit Rules

- Prompts use clear imperative voice and tell the user what to substitute.
- Plain-language product context first (per writing-style rule).
- Keep prompts focused: one outcome per prompt.

## Required Checks

- Em-dash rule applies.
- No team-internal references in prompts intended for general use.
- Prompts that reference other prompts use plain markdown links.

## Required Skills

- None mandatory.

## Do Not

- Inline secrets or environment-specific values.
- Use ticket IDs in the prompt body (per no-ticket-ids-in-code rule, which extends to docs).

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a prompt or when its expected substitutions change.
