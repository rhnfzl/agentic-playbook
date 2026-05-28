# Atlas

`docs/atlas/` is the **auto-generated knowledge graph** of every ADR, skill, and trajectory in the playbook plus the cross-references between them. Per ADR-0049.

## How to use it

```bash
make atlas               # rebuild the site
open docs/atlas/index.html   # browse (macOS); xdg-open on Linux
```

The index page lists every node by kind (ADRs, skills, trajectories) with badges that summarize the security signal (AI BOM `.vetted-as-of`), the freshness signal (last_reviewed), and (with `TELEMETRY=on`) the usage signal (trigger count + p95 latency). Click any node to see its full page; the page links to every other node it references.

## What gets generated

| File or directory | What it is |
|---|---|
| `index.html` | Top-level browse view: ADRs (49), skills (109), trajectories (1). |
| `graph.json` | Machine-readable graph payload (nodes + edges); count varies with the corpus size at build time. |
| `static/` | CSS + JS for the site. |
| `adr/<NNNN>.html` | One HTML page per ADR, with backlinks to skills + trajectories that reference it. |
| `skill/<category>-<name>.html` | One HTML page per skill, with backlinks to ADRs that mention it + the skill's trajectories. |
| `trajectory/<skill>-<scenario>.html` | One HTML page per trajectory, linked to its skill. |

Do not hand-edit anything under `docs/atlas/`; `make atlas` will overwrite. The single hand-authored file in this subtree is `README.md` (this file).

## Why this exists

The playbook's value proposition is "the rationale IS the value." 49 ADRs is a lot of pages to navigate file-by-file. Atlas is the affordance that makes browsing 49 + 140 + 8 = ~200 interlinked artifacts feasible.

ADR-0049 documents the design choices: why auto-generated (because the corpus moves faster than hand-curated indexes survive), why static HTML (because GitHub Pages or any other static host can serve it), why a graph (because the value is in the cross-references, not the per-file content).

## Privacy contract

Telemetry signals (per-skill trigger count, latency, token counts) are rendered into the atlas pages ONLY when `TELEMETRY=on` is set explicitly at build time. The default and `TELEMETRY=off` both omit the telemetry badges. This is intentional: atlas pages get committed to the repo, and a contributor running the OTel collector locally should not have their personal usage signal bake into pages headed to PRs.

See ADR-0049's privacy section and `scripts/atlas/README.md` for the implementation.

## Build cadence

`make atlas` is not run by CI today. The current contract is "atlas regenerates on demand; the maintainer commits the rebuilt site when the underlying corpus changes." A future ADR may add a CI gate that compares the committed atlas against a fresh build and blocks on drift.

## Browsing without rebuilding

The committed copy in this repo is the maintainer's latest build. Clone the repo and open `docs/atlas/index.html` directly; no `make` required.
