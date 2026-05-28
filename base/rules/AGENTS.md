# Rules

Owner: Rehan
last_reviewed: 2026-05-27

## Purpose

Always-on behavioral constraints. A rule is unconditional; a skill is conditional. If you find yourself writing "when X, do Y" it belongs in `skills/`, not here.

## What Lives Here

- Generic rule files at `base/rules/`: never-push-to-develop, no-em-dashes, no-ticket-ids-in-code, writing-style.
- team-specific rule files at `overlays/<name>/rules/` (per ADR-0040): vcs-not-github, direct-acc-first, full-request-chain, jira-priority-scheme, label-policy, mcp-first-boundary.
- `README.md` documents the rule contract and installer behavior.

## Local Commands

- Installer concatenates selected rules into the per-target AGENTS.md.
- Rules can also be invoked as standalone references.

## Edit Rules

- One rule per file. Short, declarative, no procedural steps.
- Title is a noun phrase ("No em dashes"), not a verb phrase.
- Body has: what the rule says, why it exists, how to apply it.
- Plain-language product context first.

## Required Checks

- Frontmatter not required for rules; em-dash check + decay (date in file) still apply.
- Cross-check that the rule does not duplicate a skill.

## Required Skills

- None mandatory.

## Do Not

- Promote a rule from a skill body without removing the skill content.
- Land a team-specific rule in `base/rules/`. Strong markers (R8-/MATCH- ticket IDs, team org name, internal hostnames, VCS.org) belong under `overlays/<name>/rules/` per ADR-0040; `scope_boundary.py` enforces this. A universal rule that uses team as a CONCRETE EXAMPLE (e.g. `never-push-to-develop.md`) stays in `base/` and is allowlisted with rationale in `scripts/checks/scope_boundary_allowlist.toml`.
- Use multi-page rules. If it needs subsections beyond what/why/how, it is a skill.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding or rewriting a rule.
