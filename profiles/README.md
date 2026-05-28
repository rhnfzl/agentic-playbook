# Profiles

This directory holds per-role bundles. A profile names a set of skills, rules, hooks, and MCP configs that ship together for a specific kind of teammate (backend developer, frontend developer, QA, tech lead, product manager, research, DevOps).

Profiles are an opinionated subset of the playbook. The full playbook may have 120+ skills, but a frontend developer only needs ~15 of them. Profiles bundle the right subset so a new joiner does not have to triage.

Per the profile-separation principle, each profile is single-role. A teammate who wears multiple hats (e.g. PM + research + developer) installs multiple profiles at once via the Makefile: `make install PROFILE=product-manager,research,backend-developer`. Direct script invocation uses the standard `--profile` flag: `python3 scripts/install.py --profile product-manager,research,backend-developer`. Either form unions the includes from each profile and dedupes; the lockfile records the resolved list so `make update` repeats the same composition.

## What ships in this directory

| Profile | Audience | Default content selection (public-safe subset) |
|---|---|---|
| `backend-developer.toml` | Backend developers | ci-failure-triage + post-iter-review + improve-codebase-architecture + tdd + triage + grill-me + handoff + write-a-skill, always-on rules, lint-guard + never-push-to-develop + human-html-autoindex hooks, code-review-graph + slack + tavily MCPs |
| `frontend-developer.toml` | Frontend developers | code-review-graph-first + post-iter-review + frontend-slides + grill-me + handoff + write-a-skill, always-on rules, lint-guard + never-push-to-develop + human-html-autoindex hooks, slack + tavily MCPs |
| `qa.toml` | QA engineers | ci-failure-triage + triage + grill-me + handoff + grill-with-docs, always-on rules, human-html-autoindex hook, slack + tavily MCPs |
| `tech-lead.toml` | Tech leads | All engineering + observability + key productivity + meta skills, always-on rules, full hook set, code-review-graph + slack + tavily MCPs |
| `product-manager.toml` | Product managers | 15 vendored PM-execution skills under `imported/pm-curated/` + meta lifecycle skills + handoff + grill-me, always-on rules, human-html-advisory + agent-memory-session-brief hooks, slack + tavily MCPs |
| `research.toml` | Researchers | 7 vendored research skills under `imported/research-curated/` + meta lifecycle skills + handoff + grill-me, always-on rules, human-html-advisory + agent-memory-session-brief hooks, tavily + slack MCPs |
| `devops.toml` | DevOps engineers | observability skills (ha-alert-triage, market-audit-deployed-stack) + meta lifecycle skills + handoff, always-on rules, never-push-to-develop + agent-memory-session-brief hooks, slack MCP. Workplace-specific DevOps skills (cloud-secrets, CI debugging, dashboard verification) are designed in the upstream and not shipped in this public mirror. |

## Schema

Each profile is a TOML file:

```toml
name = "backend-developer"
description = "Backend developer profile (public-safe subset)."
owner = "rehan"
last_reviewed = "2026-05-28"

[skills]
include = [
  "engineering/ci-failure-triage",
  "engineering/post-iter-review",
  # ...
]

[rules]
include = [
  "never-push-to-develop",
  "no-em-dashes",
  "no-ticket-ids-in-code",
  "writing-style",
]

[hooks]
include = [
  "lint-guard",
  "never-push-to-develop",
  "human-html-autoindex",
]

[mcp]
include = [
  "code-review-graph",
  "slack",
  "tavily",
]
```

Required: `name`, `description`. The four `[<type>] include = [...]` tables are all optional; omitting one means "no entries for this content type, install nothing matching" (rather than "install everything"; the installer's no-`--profile` mode is the unfiltered path).

Referenced items (skills, rules, hooks, MCP slugs) MUST exist in the playbook. The installer warns loudly when a profile lists entries that no longer resolve (renamed or deleted upstream).

## How the installer uses profiles

As of ADR-0025, profiles are wired end-to-end:

- `python3 scripts/install.py --profile backend-developer` narrows the global install to the backend-developer skill / rule / hook / MCP lists. Adapters only see the filtered content.
- `python3 scripts/playbook_init.py --target /path --profile backend-developer` records the profile name in the target's `.playbook-config.yaml` and scaffolds the pointer AGENTS.md. Future per-project content materialization reads the same Profile.
- Omitting `--profile` installs everything (today's default behavior preserved).

Agents (subagents), slash commands, and prompts pass through filtering unchanged. The Profile constrains only the four canonical types it lists today (skills / rules / hooks / mcp).

## How to add a profile

1. Identify a real audience (named teammates, role with 3+ people, distinct workflow).
2. Create `profiles/<slug>.toml` with the schema above.
3. Pick skills / rules / hooks / MCP from the playbook directories. Use slugs (e.g., `engineering/post-iter-review`), not full paths.
4. Set `owner:` to an OWNERS.md alias or individual handle.
5. Run `make check` (em-dash lint covers `profiles/*.toml`).
6. PR per `CONTRIBUTING.md`.

## Quality bar (per ADR-0011)

- A profile must represent ≥3 people OR a clearly distinct workflow. Solo-person profiles are personal config, not team-shared bundles.
- Skills / rules / hooks referenced in the profile MUST exist in the playbook (no dangling references).
- A profile's content selection should be reviewable in <5 minutes: too long means the profile is unfocused.
- Profile decay tracks the same `last_reviewed` discipline as skills. Refresh quarterly.

## References

- ADR-0005: Tier 1 / 2 / 3 adapter scheme (parallel idea: tier classification of agents; profile is the analogous classification of teammates)
- `OWNERS.md` for the team alias registry profile owners reference
