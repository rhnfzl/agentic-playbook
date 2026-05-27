# 0015. Skill size policy (warn 500, block 1000) + progressive disclosure

## Status

Accepted (2026-05-25)

## Context

Anthropic and agentskills.io guidance both recommend keeping the main SKILL.md compact (loaded into context on activation). Long SKILL.md files burn token budget on content the workflow may not need.

v0.2.1 inventory found 8 SKILL.md files >= 500 lines:
- `skills/meta/graphify/SKILL.md` (1291 lines)
- `skills/research/notebook-to-production/SKILL.md` (543)
- `skills/research/literature-synthesis/SKILL.md` (536)
- `skills/research/agent-repo-briefing/SKILL.md` (526)
- `skills/research/hypothesis-design/SKILL.md` (520)
- `skills/research/statistical-analysis/SKILL.md` (514)
- `skills/research/rag-eval-method/SKILL.md` (510)
- `skills/research/data-profiling/SKILL.md` (500)

Most are just barely over a soft guideline; graphify is genuinely egregious.

## Decision

`scripts/size_check.py` enforces a two-tier policy:

| Threshold | Severity |
|---|---|
| >= 500 lines | WARN (encourage progressive disclosure) |
| >= 1000 lines | BLOCK (must split before merge) |

Vendored skills (`skills/imported/`) are WARN-only at both thresholds (per ADR-0019: upstream optimizes differently, and our authored-content discipline does not extend to them).

## Progressive disclosure pattern

When a SKILL.md crosses 1000 lines, split into:

- `<skill>/SKILL.md`: the trigger file (when-to-use, when-not-to-use, brief workflow skeleton, pointers to references)
- `<skill>/references/<topic>.md`: deep procedure per topic (loaded only when the workflow needs that depth)
- `<skill>/scripts/<helper>.<sh|py>`: deterministic helpers (run, not read)

The trigger file routes decisions. References hold the depth.

## v0.3 outcome

`skills/meta/graphify/SKILL.md` split from 1291 to 369 lines via 5 reference files (`extraction.md`, `exports.md`, `incremental.md`, `query-modes.md`, `integrations.md`). All behaviour preserved.

The 8 other 500-543 line skills ship with warnings only; future PRs split them when touched.

## Consequences

- Authored skill PRs that introduce a >1000-line SKILL.md cannot land.
- Vendored content can carry larger files (taste-skill image-to-code-skill is 1231 lines; imagegen-frontend-mobile is 1468 lines). Catalog notes flag the trade-off.
- Future iterations can lower BLOCK to 800 or 500 once the warning-only skills are split.

## Exception policy (v0.8 amendment)

`scripts/size_check.py:LONGFORM_EXCEPTIONS` lists first-party skills explicitly exempted from the 500-line warn threshold. Each entry must pair the path with a justification that explains why progressive disclosure would *worsen* the skill (typically: the deep content references and the trigger checklist are tightly coupled, and splitting fragments the worked example from the rule it illustrates). Reviewers should challenge entries whose justification reads as "I did not want to split it"; legitimate entries describe a structural reason.

Vendored skills under `skills/imported/` are surfaced informationally only; they do not count toward the warn total because their length is upstream's choice and `docs/research/external-skill-sources.md` already documents the trade-off.

The BLOCK threshold (1000 lines) is unchanged and applies to every first-party skill regardless of LONGFORM_EXCEPTIONS membership.

## Related

- v0.3 plan: scope row 6
- Anthropic Agent Skills best practices: progressive disclosure section
