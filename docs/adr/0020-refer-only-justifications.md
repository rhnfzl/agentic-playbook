# 0020. Refer-only justifications for evaluated sources

## Status

Accepted (2026-05-25)

## Context

v0.3 evaluated more external sources than it vendored. The catalog (`docs/research/external-skill-sources.md`) records every evaluated source so the reasoning is recoverable, but the rejection rationale for high-profile sources deserves an ADR so future reviewers do not re-litigate the same decision.

## Decision

The following sources are catalogued as `refer-only` with explicit reasons:

### Legal blockers (cannot legally redistribute)

| Source | Issue |
|---|---|
| `gnurio/refactoring-ui-plugin` | License text says "all rights reserved". No OSS license. |
| `nickwinder/synthteam` | No LICENSE file present. No redistribution right. |
| `multica-ai/andrej-karpathy-skills` | No LICENSE file present. No redistribution right. |
| `alexgreensh/token-optimizer` | PolyForm Noncommercial license. team is commercial; cannot vendor. |

### Strategic / fit-based rejections

| Source | Reason |
|---|---|
| `anthropics/skills/frontend-design` | Apache 2.0 (vendorable), but prose-only design guidance. Newer ecosystem moves frontend work through MCP-connected approaches (chrome-devtools-mcp, design-system MCPs, v0). Redundant with Layers + Impeccable + Taste already vendored. |
| `vercel-labs/agent-skills web-design-guidelines` | Deferred to v0.4 after Impeccable use proves the gap. |
| `microsoft/AI-Engineering-Coach` | MIT, but it is a VS Code extension that reads local AI session logs (observability tool), not a skill source. Listed in `TOOLS.md` instead. |
| `microsoft/azure-skills` | MIT, conditional. Relevant only when team picks up Azure workflows. |
| `supabase/agent-skills` | MIT, conditional. Relevant only for Supabase/Postgres workflows. |
| `github/awesome-copilot` | Catalog of Copilot patterns; reference for Tier 2/3 adapter research, not a direct installer target. |

### Reference-only (concept borrows)

| Source | Reason |
|---|---|
| `steipete/agent-scripts` | MIT. Used as a structural benchmark; the playbook absorbs `validate-skills`, `tools.md`, `CHANGELOG.md`, `RELEASING.md` patterns. Do not vendor whole. |
| `microsoft/apm` | MIT. Best observed manifest + lockfile + drift model. Playbook borrows the concepts (per ADR-0016) without adopting the schema. |
| `intellectronica/ruler` | Adapter reference for path/format research. ADR-0003 records the decision to own the playbook installer rather than depend on Ruler. |
| `agentsmd/agents.md` | Upstream AGENTS.md format project. The playbook aligns (ADR-0013) and will contribute upstream (ADR-0021). |

## Consequences

- Each refer-only source has a documented reason in the catalog and (for the high-profile ones) here.
- Future PRs proposing to vendor any of these sources must address the documented blocker (or document why the blocker no longer applies, e.g. upstream relicenses MIT).
- Legal-blocker sources can be revisited if upstream adds a permissive license; strategic-rejection sources can be revisited if the fit changes.

## Related

- ADR-0014 (external-source policy)
- ADR-0019 (vendored sources)
- `docs/research/external-skill-sources.md` (canonical catalog)
