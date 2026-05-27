---
name: docs-drift
description: Use when checking the team workspace for documentation-lifecycle drift. Scans every authored markdown file, flags missing frontmatter, schema violations, path/type mismatches, and generated-artifact retention violations. Advisory only - does not block. Invoke at the start of any doc-related session, and as part of the quarterly /audit-docs sweep.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# docs-drift

## When to use

Invoke when any of these applies:
- Starting work on documentation in this workspace
- Verifying compliance before a subproject PR that includes markdown changes
- Quarterly audit (called by /audit-docs)
- When /docs-index --check reports a difference

## Invocation

```bash
python3 ~/.agents/skills/docs-drift/__main__.py [--root PATH] [--fix-interactive]
```

- `--root PATH` - workspace root to scan (default: current directory)
- `--fix-interactive` - walk each finding and apply proposed fix on y/n

## What it reports

1. Files missing frontmatter (expected but not present)
2. Files with malformed frontmatter (fails schema parse)
3. Files whose `type` does not match the path's expected type (per DOCS_CONVENTIONS.md)
4. Generated-artifact directories exceeding retention (keep 10 per kind + 30-day window)

Exits 0 regardless of findings (advisory). The v0.1 output is plain text; a `--format json` flag may be added later if scripting needs it.
