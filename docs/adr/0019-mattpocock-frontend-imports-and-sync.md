# 0019. Mattpocock + frontend imports + sync mechanism

## Status

Accepted (2026-05-25)

## Context

v0.3 vendors external skills for the first time (mattpocock/skills full set, plus three frontend pilots: layers, impeccable, taste-skill). Without explicit policy, vendored content drifts: dirnames may not match upstream `name`, licenses may not match SPDX, frontmatter may lack our required fields.

## Decision

### Vendor layout

Each external source lives at `skills/imported/<source>/`. Sources keep their upstream skill subtree structure:

- `skills/imported/mattpocock/{engineering,productivity,misc}/<skill>/SKILL.md`
- `skills/imported/layers/<skill>/SKILL.md` (9 skills, all `layers-*` named)
- `skills/imported/impeccable/SKILL.md` (single canonical skill)
- `skills/imported/taste-skill/<skill>/SKILL.md` (12 skills)

### Local modifications (the only diff from upstream)

Each vendored SKILL.md gets three frontmatter fields injected (if not present):

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: <vendor date>`

Body content is never modified.

### Lint relaxations for vendored content

`scripts/frontmatter_lint.py` and `scripts/size_check.py` recognize `VENDORED_PREFIX = "skills/imported/"`:

- Skip parent-dir-match check (upstream naming may differ from dirname; e.g. taste-skill/taste-skill/ contains `name: design-taste-frontend`)
- Skip license SPDX validation (upstream uses arbitrary strings, attribution prose, etc.)
- Skip allowed-tools known-name validation (upstream may use non-standard tool patterns)
- Warn-only for size violations >1000 lines (authored content still blocks at 1000)

`scripts/check_em_dashes.py` uses `VENDORED_PREFIXES = ("mcp/anchored-fs/", "skills/imported/")` to skip vendored content entirely from prose style rules.

### Sync mechanism

`scripts/sync_mattpocock.sh` runs monthly (or on demand) to pull upstream changes:

1. Shallow clone upstream into a temp dir.
2. Compare new pin against the one in `skills/imported/mattpocock/PROVENANCE.md`.
3. Rsync `engineering/ productivity/ misc/` into `skills/imported/mattpocock/`.
4. Re-inject version/owner/last_reviewed; bump last_reviewed to today.
5. Update PROVENANCE.md pin SHA.
6. Print diff for review.

Other frontend pilots (layers/impeccable/taste-skill) have lower upstream activity; manual refresh per release using the same pattern.

### PROVENANCE.md per vendored source

`skills/imported/<source>/PROVENANCE.md` records: upstream URL, license, pin SHA at vendor time, vendored subtree(s), local modification list, sync workflow, catalog status.

## Anthropic frontend-design exception

Anthropic frontend-design was vendored briefly during v0.3 PR development then DROPPED after user evaluation. Catalog entry retained as refer-only with rationale (prose-only design guidance; better served by MCP-connected approaches; redundant with Layers + Impeccable + Taste). See `docs/research/external-skill-sources.md` for the full reasoning.

## Consequences

- Adding a new external import = vendor + write PROVENANCE.md + add catalog row + run `make audit` + run `make check`.
- v0.3 brings skill count from 58 to 98 (+40 vendored).
- Monthly sync motion stays low-effort; teammates run `make sync-mattpocock` and review the diff.

## Related

- ADR-0014 (external-source policy: catalog + audit)
- ADR-0020 (refer-only justifications)
- v0.3 plan: scope row 9 + 10
