# pbakaus/impeccable (vendored)

Owner: Rehan
last_reviewed: 2026-05-25

## Source

- Upstream: https://github.com/pbakaus/impeccable
- License: Apache 2.0
- Pin (initial vendor): `84135db0e6bdd58d22828f7bc8331cae7bde3e7f`
- Vendored on: 2026-05-25
- Vendored subtree: `skill/` (the canonical single-skill source; adapter copies under `.cursor/`, `.gemini/`, etc. were ignored)

## Local modifications

Original `name`, `description`, `argument-hint`, `user-invocable`, `allowed-tools`, and license fields preserved as-is. Vendoring step injects:

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: 2026-05-25`

No body content modified.

## Sync

No automated sync script (single-skill upstream, manual review per release).

## Status

Per `docs/research/external-skill-sources.md`: `recommended`, `risk_class=docs-only`.
