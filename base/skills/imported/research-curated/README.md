# imported/research-curated/

Curated subset of research-flavored skills from the same two upstream PM collections that feed `base/skills/imported/pm-curated/`. Research is a separate playbook profile (per the profile-separation principle): a dev who installs `--profile research` gets only the research bundle, not the PM execution bundle.

## What ships here

| Skill | What it does |
|---|---|
| `competitor-analysis/` | Structured competitor analysis: feature matrix, positioning, weaknesses. |
| `discover-interview-synthesis/` | Synthesize a set of discovery interviews into themes + open questions. |
| `interview-script/` | Author a structured discovery interview script with non-leading question shape. |
| `market-sizing/` | Build a top-down + bottom-up market sizing estimate with explicit assumption tracking. |
| `sentiment-analysis/` | Analyze sentiment across a corpus (reviews, NPS comments, support tickets) with category breakdown. |
| `summarize-interview/` | Summarize one interview into themes, quotes, and follow-up questions. |
| `user-personas/` | Build user personas grounded in interview data, not vibes. |

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md) for the upstream URLs, license, and pin SHAs.

These skills are **vendored** (per ADR-0014 + ADR-0018): the playbook copies them locally.

## How these relate to `pm-curated/`

- `pm-curated/` is PM execution: PRDs, sprint plans, retros, roadmap.
- `research-curated/` is PM discovery and research: interviews, personas, competitor analysis, market sizing.

A dev who plays both roles installs `--profile research,product-manager`; the installer unions the includes and dedupes.

## When to consume

Use `make install PROFILE=research` to get this set. The `research` profile also pulls in `base/skills/research/` (the team-authored rigor skills like data-profiling, RAG eval), so the installed set is the union.

## When to NOT consume

If your work is engineering-only (no discovery, no analysis, no synthesis), use a different profile. The `research` profile's MCP set (Tavily for web search) is also overkill for pure-engineering work.

## Related

- [`PROVENANCE.md`](PROVENANCE.md) for upstream attribution.
- `base/skills/imported/pm-curated/README.md` for the sibling PM execution bundle.
- `base/skills/research/README.md` for the team-authored research skills.
- `profiles/research.toml` for the profile composition.
