# 0021. Contribute back to agentsmd/agents.md upstream

## Status

Accepted (2026-05-25); execution scheduled post-v0.3 ship

## Context

`agentsmd/agents.md` is the upstream AGENTS.md format project (MIT, stewarded by the Agentic AI Foundation under the Linux Foundation). The playbook's v0.3 governance harness (ADR-0013) implements nested-coverage checks, size budgets, locality enforcement, and conflict-control that upstream documents informally but does not enforce.

The v0.3 grilling decision was "yes, contribute back after v0.3 ships".

## Decision

Post-v0.3 work-stream files PRs to `agentsmd/agents.md`:

### Concrete proposals

1. **Nested coverage examples.** Add a documented example showing per-subdirectory AGENTS.md with size budget (root 80-140, sub 25-80), local-commands section, edit-rules section, locality rule.

2. **8-section template.** Submit the strict template (Purpose / What Lives Here / Local Commands / Edit Rules / Required Checks / Required Skills / Do Not / Owner And Freshness) as a recommended (not required) scaffold.

3. **Harness check patterns.** Document the four classes of automated check we found valuable: coverage / length / locality / freshness. Frame as "what teams enforcing AGENTS.md as code can verify" rather than format additions.

4. **Conflict-control marker.** Propose the `<!-- conflict-with-root: justified -->` HTML comment as a standard escape hatch when a sub-AGENTS.md legitimately overrides a root rule.

### Out of scope for upstream contribution

- The audit script (`scripts/audit_external_skill.py`) is playbook-specific (security policy) and not appropriate for the format spec.
- The lockfile schema (`.playbook-lock.json`) is installer-specific.
- The eval harness is skill-specific, not AGENTS.md-specific.

## Process

1. Wait for v0.3 to merge and be in use for ~2 weeks (validate the harness in practice).
2. Open one upstream issue per proposal to gauge interest before authoring PRs.
3. Submit PRs serially, smallest first (template scaffold, then nested coverage, then harness patterns, then conflict marker).
4. Track upstream discussion; update this ADR if proposals are rejected or modified.

## Consequences

- Visibility for the playbook's governance approach.
- Validates patterns externally; if upstream pushes back on a proposal, that's signal to revisit our own implementation.
- Maintenance burden (responding to upstream review). Bounded by serial submission.

## Related

- ADR-0013 (AGENTS.md governance harness in playbook)
- v0.3 plan: scope row 12
- `docs/research/external-skill-sources.md` (agentsmd/agents.md entry)
