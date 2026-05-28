# imported/pm-curated/

Curated subset of two upstream PM skill collections. The playbook hand-picks high-leverage PM execution skills (PRD scaffolding, sprint planning, OKR brainstorming, retros, prioritization, stakeholder mapping, meeting summarization) so the `product-manager` profile ships a tight bundle rather than the union of all upstream PM skills.

## What ships here

Each subdirectory is one skill. Categories represented: PRD authoring, OKR + roadmap, prioritization, problem definition, sprint + retro mechanics, stakeholder mapping, meeting + interview summarization, release notes, user stories, opportunity-solution trees, pre-mortems, PM-critic.

See the directory listing for the exact set; new imports surface here as the upstream collections grow.

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md) for the upstream URLs, license, pin SHAs, and `last_reviewed` date.

These skills are **vendored** (per ADR-0014 + ADR-0018): the playbook copies them locally rather than fetching at install time. Vendoring keeps install offline-capable, makes the supply-chain gate's audit (`make audit`) feasible, and lets the maintainer scrub workspace-specific examples before publishing.

`scripts/sync_curated_skills.py` (invoked via `make sync-curated-skills`) refreshes the vendored copy from the pinned upstream SHA. The refresh is opt-in; new content does not auto-land.

## How these relate to `productivity/` and `research/`

- `productivity/` ships team-authored or workflow-discovery-driven skills. They're general workflow tools that don't fit a single role.
- `research/` ships rigor-flavored skills (data profiling, lit synthesis, RAG eval) that PMs may use but engineers and data scientists also use.
- `imported/pm-curated/` ships the PM execution surface specifically. The `product-manager` profile selects this set; the `research` profile selects `imported/research-curated/` instead.

## When to consume

Use `make install PROFILE=product-manager` to get this set materialized into your coding agent. Direct copy of individual skill directories is also supported; the SKILL.md format is documented in `base/skills/README.md`.

## When to NOT consume

If you only need one skill (e.g. just `create-prd/`), copy that one subdirectory directly into your own playbook's `base/skills/<your-category>/<skill-slug>/`. Don't drag the whole bundle in unless you want the bundle's workflow coherence.

## Related

- [`PROVENANCE.md`](PROVENANCE.md) for upstream attribution and pin tracking.
- `base/skills/README.md` for the skill format.
- `base/skills/imported/research-curated/README.md` for the sibling research bundle.
- `profiles/product-manager.toml` for the profile that filters to this set.
