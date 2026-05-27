# 0013. AGENTS.md governance harness

## Status

Accepted (2026-05-25)

## Context

v0.2.1 shipped 2 AGENTS.md files (root + `skills/engineering/supacode-cli/AGENTS.md`) against ~10 first-class editable directories. Agents had to infer per-directory conventions from a single root file. Research findings (`docs/human-html/2026-05-25-research-coding-agents-playbook-improvement-research.html`) and AGENTS.md upstream guidance both point to nested AGENTS.md as the standard pattern.

Sparse coverage means agents either work from a too-broad root contract or invent local rules silently.

## Decision

`scripts/check_agents_md.py` enforces six checks on every AGENTS.md, with block-by-default severity (v0.3 plan locked decision):

| Check | Rule | Severity |
|---|---|---|
| Coverage | Every first-class top-level dir (agents/, commands/, docs/, hooks/, mcp/, profiles/, prompts/, rules/, scripts/, skills/) has an AGENTS.md | BLOCK |
| Length: root | warn >200, BLOCK >300 lines | BLOCK |
| Length: sub | warn >120, BLOCK >180 lines | BLOCK |
| Required sections | 8 headings (Purpose / What Lives Here / Local Commands / Edit Rules / Required Checks / Required Skills / Do Not / Owner And Freshness) | BLOCK |
| Locality | sub-AGENTS.md <40% line-overlap with root | BLOCK |
| Freshness | 90d for active code dirs, 180d for docs/template dirs | BLOCK |
| Conflict control | direct contradictions between root and sub flagged unless sub carries `<!-- conflict-with-root: justified -->` | BLOCK |

`.agents-md-ignore` at repo root accepts per-path exemptions. v0.3 ships this file EMPTY: full coverage is authored before the gate flips on.

Subtree marker warning (presence of pyproject.toml / package.json / Makefile / Dockerfile / SKILL.md without a nearby AGENTS.md) is WARN, not block.

## Consequences

- v0.3 PR includes 10 new AGENTS.md files closing the coverage gap.
- Future PRs that add a top-level directory must also author its AGENTS.md before they can land.
- Subdir contradiction patterns (`feedback_no_em_dashes`, `rules/never-push-to-develop.md`) are baseline-checked; intentional overrides require the HTML comment marker.
- Existing skill-specific AGENTS.md files in `skills/<cat>/<skill>/AGENTS.md` are still optional (covered by the SUBTREE warn).

## Related

- v0.3 plan artifact: `docs/human-html/2026-05-25-plan-v0-3-coding-agents-playbook-roadmap.html`
- Upstream format: https://github.com/agentsmd/agents.md (ADR-0021 covers contribution back)
