# Profiles

This directory holds per-role bundles. A profile names a set of skills, rules, hooks, and MCP configs that ship together for a specific kind of teammate (backend developer, frontend developer, QA, tech lead, product manager, research, DevOps).

Profiles are an opinionated subset of the playbook. The full playbook may have 120+ skills, but a frontend developer only needs ~15 of them. Profiles bundle the right subset so a new joiner does not have to triage.

Per the profile-separation principle, each profile is single-role. A teammate who wears multiple hats (e.g. PM + research + developer) installs multiple profiles at once via the Makefile: `make install PROFILE=product-manager,research,backend-developer`. Direct script invocation uses the standard `--profile` flag: `python3 scripts/install.py --profile product-manager,research,backend-developer`. Either form unions the includes from each profile and dedupes; the lockfile records the resolved list so `make update` repeats the same composition.

## What ships in this directory

| Profile | Audience | Default content selection |
|---|---|---|
| `backend-developer.toml` | AI Backend / MCP engineers | All engineering skills + backend-relevant rules + Sonar + VCS hooks + Jira/Slack/error-tracking MCP |
| `frontend-developer.toml` | Frontend engineers | UI + presentation skills + VCS hooks + Slack MCP |
| `qa.toml` | QA engineers | Test-discipline skills + bug-triage + VCS-pr-review + Jira MCP |
| `tech-lead.toml` | Tech leads | Everything in backend + meeting-brief + handoff + stakeholder-slack-brief + presentation + decay tooling |
| `product-manager.toml` | Product managers | 15 curated PM skills (PRD, sprint, retro, roadmap, prioritization, stakeholder map) + AGENTS.md curator + Jira/Slack/Tavily MCP |
| `research.toml` | Researchers, PMs running discovery | 7 research-curated skills (interview script + synthesis, competitor analysis, user personas, market sizing) + Tavily MCP |
| `devops.toml` | DevOps engineers | 4 team-native DevOps skills (Secrets Manager configmap apply, error-tracking triage, k8s dashboard verify, CI pipeline debug) + observability helpers + error-tracking/code-quality/Atlassian/Slack MCP. External tools (Terraform, Packer, generic k8s skills) documented in `devops.README.md` for opt-in install. |

## Schema

Each profile is a TOML file:

```toml
name = "backend-developer"
description = "AI Backend and MCP engineers at team"
owner = "backend-team"
last_reviewed = "2026-05-24"

[skills]
include = [
  "engineering/post-iter-review",
  "engineering/VCS-pr-review",
  "engineering/ci-failure-triage",
  # ...
]

[rules]
include = [
  "never-push-to-develop",
  "mcp-first-boundary",
  "no-ticket-ids-in-code",
  # ...
]

[hooks]
include = [
  "never-push-to-develop",
  "lint-guard",
  "sonar-advisory",
]

[mcp]
include = [
  "atlassian",
  "VCS",
  "error-tracking",
  "slack",
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
