# jamiemill/layers-skills (vendored)

Owner: Rehan
last_reviewed: 2026-05-25

## Source

- Upstream: https://github.com/jamiemill/layers-skills
- License: MIT
- Pin (initial vendor): `0e5d49b5840a542fd59c0a64f4ba0013c30160fe`
- Vendored on: 2026-05-25
- Vendored subtree: `skills/` (the full upstream skill set; 9 skills)

## Local modifications

Each vendored SKILL.md retains its original `name` and `description`. The playbook installer requires the standard frontmatter shape, so the vendoring step injects:

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: 2026-05-25`

No body content modified.

## Sync

No automated sync script for Layers (low upstream activity; manual review per release). To refresh:

```bash
cd /tmp && rm -rf layers-vendor && git clone --depth 1 https://github.com/jamiemill/layers-skills layers-vendor
rsync -a /tmp/layers-vendor/skills/ skills/imported/layers/
# Re-inject owner/version/last_reviewed via scripts/sync_mattpocock.sh pattern
```

## Status

Per `docs/research/external-skill-sources.md`: `recommended`, `risk_class=docs-only`.
