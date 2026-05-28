# observability/

Operations, monitoring, debugging, alert triage. Skills here help the coding agent work with deployed systems: error trackers, dashboards, log queries, infrastructure state.

## What ships here

| Skill | What it does |
|---|---|
| `ha-alert-triage/` | Triage a Home Assistant (or analogous home-automation) alert: classify, locate the device or service, propose a fix or escalation. |
| `market-audit-deployed-stack/` | Survey the current best-of-breed stack for a deployed system's category (database, queue, observability, etc.) so a refactor or replacement is evidence-driven. |

## When to add an observability skill

- The workflow involves a deployed system (not local development).
- The workflow involves reading signal (alerts, metrics, logs, traces) and producing a structured next step.
- The workflow has a deterministic shape that's not yet covered by the team's runbook or the on-call playbook.

For engineering workflows that fix the underlying code, use the engineering/ category. For DevOps workflows that touch infrastructure (CI pipelines, secrets, k8s configs), use the devops profile's external tool catalog rather than authoring observability skills.

## What's deliberately not here yet

- A `sentry-issue-triage/` skill that mirrors the team's internal Sentry triage workflow lives in `overlays/team/` (per ADR-0040), not `base/`. The base version of error-tracking triage is intentionally generic.
- Cloud-provider-specific dashboards (AWS CloudWatch, GCP Cloud Monitoring) are out of scope for `base/` because their UX and CLI differ enough that one skill would always overfit to one provider.

## Related

- `base/skills/README.md` for the skill format and category contract.
- `base/mcp/README.md` for the error-tracking / Atlassian / code-quality MCP server configs that observability skills typically depend on.
- ADR-0040 (base / overlay split) for why team-specific observability skills live in overlays.
