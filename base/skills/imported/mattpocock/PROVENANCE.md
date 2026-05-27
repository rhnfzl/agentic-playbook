# mattpocock/skills (vendored)

Owner: Rehan
last_reviewed: 2026-05-25

## Source

- Upstream: https://github.com/mattpocock/skills
- License: MIT
- Pin (initial vendor): `b8be62ffacb0118fa3eaa29a0923c87c8c11985c`
- Vendored on: 2026-05-25
- Vendored subtrees: `skills/engineering/`, `skills/productivity/`, `skills/misc/` (excluded: `deprecated/`, `in-progress/`, `personal/`)

## Local modifications

Each vendored SKILL.md retains its original `name`, `description`, and any `argument-hint` field. The playbook installer expects the standard frontmatter shape, so the vendoring step injects three additional fields:

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: 2026-05-25`

No SKILL.md body content is modified. No scripts or references are added.

## Sync

Run `make sync-mattpocock` to pull upstream changes. The script:

1. Shallow-clones `mattpocock/skills` into a temp dir.
2. Rsyncs `engineering/`, `productivity/`, `misc/` into this directory.
3. Re-applies the version / owner / last_reviewed injection.
4. Prints a diff for review before commit.
5. Updates this PROVENANCE.md's pin SHA.

After sync, run `make audit` to re-check vendored content against the external-skill security audit (per ADR-0014).

## Status

Per `docs/research/external-skill-sources.md`: `recommended`, `risk_class=docs-only`.
