# scripts/atlas/

The knowledge-graph builder for `docs/atlas/`. Per ADR-0049.

## What ships here

| File | Role |
|---|---|
| `__init__.py` | Public exports: `build_graph`, `render_site`. |
| `graph_builder.py` | Walks the repo, enumerates ADRs / skills / trajectories, derives edges (belongs_to, mentions, references). Uses `git ls-files` so the build is reproducible from a clean checkout. |
| `template_engine.py` | Minimal stdlib-only HTML template renderer. No Jinja, no external deps. |

The build entry point lives at `scripts/build_atlas.py` (not here, kept at the top level so `make atlas` is one line).

## How `make atlas` consumes this

```
  make atlas → scripts/build_atlas.py
                    │
                    ├─ scripts/atlas/graph_builder.py
                    │    ├─ _tracked_paths() via git ls-files
                    │    ├─ _adr_nodes() walks docs/adr/*.md
                    │    ├─ _skill_nodes() walks base/skills/**/SKILL.md
                    │    ├─ _trajectory_nodes() walks base/trajectories/**/*.yaml
                    │    └─ _edges() derives belongs_to + mentions + references
                    │
                    └─ scripts/atlas/template_engine.py
                         └─ writes docs/atlas/{index.html, graph.json, adr/*.html, skill/*.html, trajectory/*.html}
```

## Privacy contract

Telemetry signals (per-skill trigger count, latency, token counts) are baked into the atlas pages ONLY when `TELEMETRY=on` is set explicitly at build time. The default and `TELEMETRY=off` both omit the telemetry badges.

This is intentional: atlas pages get committed to the repo, and a contributor running the OTel collector locally should not have their personal usage signal silently bake into pages headed to PRs. See ADR-0049's privacy section.

## Reproducibility

`_tracked_paths()` filters node enumeration to `git ls-files` output. This means untracked work-in-progress files do NOT change the committed atlas, so a maintainer's local sandbox doesn't pollute reviews.

`build_atlas.py` accepts `--out <path>` for non-default output locations (the test suite uses tmp_path). The output path may be outside the repo root; `relative_to()` is wrapped in try/except for that case.

## Identity helper

The atlas, telemetry, and decay subsystems all need to answer "what's the canonical identity of this skill?" The question is non-trivial because frontmatter `name:` may differ from directory name (in vendored skills especially). The canonical resolver lives at `scripts/skill_identity.py:skill_identity()` and is used by all three subsystems so they can't drift apart.

## What's deliberately not here yet

- **D3 force-graph view.** The current `graph.json` is consumed only by the static page renderer; a future enhancement would ship a force-graph view of the full corpus. Tracked in ADR-0049's follow-up section.
- **Atlas drift CI gate.** A future gate would compare the committed atlas against a fresh build and block on drift, so the maintainer can't accidentally ship a stale atlas. Tracked in ADR-0049's follow-up section.

## Related

- [`docs/atlas/README.md`](../../docs/atlas/README.md) for the consumer story.
- [`docs/adr/0049-why-atlas-auto-generated.md`](../../docs/adr/0049-why-atlas-auto-generated.md) for the design rationale.
- [`tests/atlas/`](../../tests/atlas/) for the test suite.
- `scripts/skill_identity.py` for the canonical skill-identity helper used by atlas + telemetry + decay.
