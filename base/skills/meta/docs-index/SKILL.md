---
name: docs-index
description: Regenerates DOCS_INDEX.md at the workspace root from every authored markdown file's frontmatter. Groups by type, sub-groups by subproject, sorts by last_reviewed descending. Run this after bulk frontmatter changes, or --check to verify the committed index matches current state.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# docs-index

## When to use

- After adding, moving, or deleting an authored markdown file
- Before a doc-related PR, to refresh the workspace-level catalog
- `--check` mode: verify DOCS_INDEX.md is up to date (no changes written)

## Invocation

```bash
python3 ~/.agents/skills/docs-index/__main__.py [--root PATH] [--check]
```

- `--root PATH` - workspace root (default: cwd)
- `--check` - exit 1 if the generated content differs from DOCS_INDEX.md; no file writes

## Output

Overwrites `<root>/DOCS_INDEX.md`. Never edits anything else.
