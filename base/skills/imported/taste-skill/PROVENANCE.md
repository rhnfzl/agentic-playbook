# Leonxlnx/taste-skill (vendored)

Owner: Rehan
last_reviewed: 2026-05-25

## Source

- Upstream: https://github.com/Leonxlnx/taste-skill
- License: MIT
- Pin (initial vendor): `c8075169cd63d1430bbf492dd4ddd478ea9fa4da`
- Vendored on: 2026-05-25
- Vendored subtree: `skills/` (the full upstream skill set; 12 skills covering taste, redesign, image-to-code, brutalist, minimalist, etc.)

## Local modifications

Original `name`, `description`, and any other upstream fields preserved as-is. Vendoring step injects:

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: 2026-05-25`

No body content modified.

Note: several taste-skill directories have a frontmatter `name:` that differs from the directory name (e.g. `taste-skill/` contains `name: design-taste-frontend`). The playbook's frontmatter_lint skips the parent-dir-match rule for vendored content (per ADR-0019). The upstream layout is preserved as-shipped.

## Sync

No automated sync script (manual review per release).

## Status

Per `docs/research/external-skill-sources.md`: `recommended`, `risk_class=docs-only`. Notes flag the opinionated nature: pair with team's restrained SaaS aesthetic for operational dashboards.
