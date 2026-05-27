# 0002. Per-subproject AGENTS.md (directory-scoped rules)

## Status
Accepted (2026-05-24)

## Context

The playbook distributes rules to team subprojects (ai-backend, mcp, tm-backend reference). Two architectures are possible:

1. **Monolithic**: one AGENTS.md at the workspace root applies to all subprojects.
2. **Per-subproject**: each subproject owns its own AGENTS.md; the playbook distributes shared rules into each one.

Initial v1 plan favored monolithic for simplicity. Then v2 research changed the call.

## Decision

Per-subproject AGENTS.md, with the playbook contributing cross-cutting rule fragments via the installer.

The installer materializes:
- team-ai-backend/AGENTS.md, base AI-Backend-specific rules + shared cross-cutting rules appended
- team_mcp/AGENTS.md, base MCP-specific rules + shared cross-cutting rules appended

Workspace-level AGENTS.md (team_LLM_Systems/AGENTS.md) stays minimal: cross-team coordination only.

## Consequences

- Each subproject's agents see only the rules relevant to that subproject. Context window stays usable.
- The playbook owns the source of truth for cross-cutting rules (label policy, no-em-dashes, etc.); subprojects own subproject-specific rules.
- Updates flow from playbook into subproject via re-running `make install`.
- Subproject-specific rules edited locally do not propagate back to the playbook automatically. That is intentional: subproject rules can diverge as the subproject's needs evolve.

## Why we changed from v1 (monolithic)

Stripe Minions research (2026): they use global rules "very judiciously" because loading all rules globally fills the context window before the agent starts work. They scope rules to subdirectories instead.

Packmind documented this as "Error #3": one-size-fits-all rules either become too generic to help or too specific to one team to be safe for others.

For team, AI Backend (Python, FastAPI, async orchestration) and MCP (Python, FastMCP, OpenAPI generation) have different conventions. A monolithic AGENTS.md applying to both would degrade context efficiency on every agent call AND give each subproject the wrong context.

## Source

- Stripe Minions writeup: ByteByteGo, 2026 ("How Stripe's Minions ship 1300 PRs")
- Packmind ContextOps research, January 2026
- See `docs/research/2026-05-24-research-brief-v2.md` for primary sources
