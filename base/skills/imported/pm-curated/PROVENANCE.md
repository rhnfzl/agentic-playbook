# pm-curated (vendored)

Owner: rehan
last_reviewed: 2026-05-26

## Source

Curated subset of two upstream PM skill collections. Per the v0.10 import-strategy
lock, the playbook hand-picks high-leverage PM skills from two MIT/Apache 2.0
sources and vendors them locally so the PM profile ships a tight, ~15-skill
bundle rather than ~128 skills with heavy overlap.

- Upstream A: `https://github.com/phuryn/pm-skills` (MIT)
  - Pin: `f9eaa51000a65e04494aeaf90355d30f2080ebf2`
- Upstream B: `https://github.com/product-on-purpose/pm-skills` (Apache 2.0)
  - Pin: `498cad9418a7ca50d0132b93ec77e8f0d66f7166`

Both repos publish well-formed `SKILL.md` files; the vendoring script copies
each picked file verbatim and injects three playbook-required frontmatter
fields (`version`, `owner`, `last_reviewed`) without modifying the body.

Vendored on: 2026-05-26

Not imported: `deanpeters/Product-Manager-Skills` (CC BY-NC-SA, non-commercial
license incompatible with internal commercial use). `derisk-ai/awesome-devops-skills`
is a metalist of other repos, not a direct skill source.

## Curated picks

The selection criteria per `SOURCES.toml`:

- High-leverage for everyday PM execution (PRD, sprint planning, roadmap,
  retro).
- Lifecycle coverage across discover, define, deliver, measure, iterate.
- Minimal overlap with `skills/imported/research-curated/` (research lives
  in its own set).
- When both upstreams have the same idea, the better-shaped version wins.

15 skills imported. See `SOURCES.toml` for the full list with upstream paths.

## Local modifications

Each vendored `SKILL.md` keeps its original `name`, `description`, and body
verbatim. The playbook installer expects three additional frontmatter
fields, which the sync script injects:

- `version: 1.0.0`
- `owner: rehan (vendored)`
- `last_reviewed: 2026-05-26`

No `SKILL.md` body content is modified. No supporting files (scripts,
references, templates) are added.

## Sync

Run `python3 scripts/sync_curated_skills.py` to pull upstream changes. The
script reads `SOURCES.toml`, clones each upstream at the pinned SHA from
`UPSTREAMS` in the script, copies + injects, and reports a diff summary.

When upstream advances, bump the pin SHA in `scripts/sync_curated_skills.py`
(`UPSTREAMS` dict) and re-run the script. Review the diff, run `make check`,
then commit.

## License compliance

- MIT (phuryn): permits redistribution provided the license + copyright
  notice ships with the source. Upstream LICENSE files are not vendored
  per file (the playbook's top-level LICENSE governs the playbook
  itself); the PROVENANCE.md you are reading cites the upstream URL +
  pin, which links the user back to the upstream LICENSE.
- Apache 2.0 (product-on-purpose): same treatment. Apache 2.0 requires
  preserving copyright + notice; the PROVENANCE.md citation satisfies
  the attribution requirement for the vendored subset.
- If the playbook ever bulk-distributes vendored skill content to a
  third party (e.g. shipping a binary install image with these skills
  baked in), the LICENSE + NOTICE files of each upstream MUST be
  bundled alongside. Inside the playbook checkout the citation chain
  is sufficient.

## Why curated, not full repo

phuryn ships 65 skills across 8 plugins; product-on-purpose ships 63 across
phases + tools + utilities. Importing both wholesale would bring ~128
skills into the playbook with heavy overlap (both have PRD, user stories,
JTBD, prioritization, etc.). The PM profile would explode to ~100 entries
and force the dev to triage on day one.

The curated approach: pick the ~15 most useful, accept that some dev
will eventually want a missing 16th skill, surface a clear "add it to
SOURCES.toml + re-sync" path for that case.
