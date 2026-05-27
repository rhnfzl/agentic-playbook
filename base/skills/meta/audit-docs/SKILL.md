---
name: audit-docs
description: Quarterly staleness sweep over every frontmattered doc. Flags (1) per-cadence stale docs (on-code-change > 90d, quarterly > 100d), (2) status:superseded > 12 months (archive candidate), (3) transient docs due for /promote-ticket review (currently age-gated; Jira status check is future work). Produces an audit report under docs/reports/snapshots/ as a new report-snapshot.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# audit-docs

## When to use

Quarterly review cadence. Can also be invoked ad hoc.

## Invocation

```bash
python3 ~/.agents/skills/audit-docs/__main__.py [--root PATH]
```

Output: `<root>/docs/reports/snapshots/audit_YYYY-MM-DD.md` with frontmatter
`type: report-snapshot, status: frozen`.
