#!/usr/bin/env python3
"""Skill size budget enforcement (ADR-0015).

Locked thresholds:
  - Warn at 500 lines (encourages progressive disclosure to references/)
  - BLOCK at 1000 lines (graphify previously sat at 1291 and had to split)

Progressive disclosure pattern: SKILL.md is the trigger file (description +
when-to-use + when-not + workflow skeleton). Deep content moves to
<skill-dir>/references/<topic>.md. Deterministic helpers move to
<skill-dir>/scripts/.

Exception policy (v0.8 D4):
  * Vendored skills under skills/imported/ are warn-tagged but NOT
    counted toward the warn total. Their length is upstream's choice;
    docs/research/external-skill-sources.md captures the trade-off.
  * First-party skills can be exempted explicitly by listing them in
    LONGFORM_EXCEPTIONS below with a documented justification. These
    are skills whose length is *intentional* (worked examples, multi-
    stage workflows, decision trees) and where progressive disclosure
    would split tightly coupled content into too many files.

Anything not in the exception list and over the warn threshold is a
real warning; anything over BLOCK_LINES is a blocking error regardless.
"""

from __future__ import annotations

import sys
from pathlib import Path

WARN_LINES = 500
BLOCK_LINES = 1000

# Vendored content (per ADR-0019). Upstream optimizes length differently;
# we surface them but do not block or count toward warn-total.
# v0.11 (ADR-0040): skills moved into base/skills/ + overlays/team/skills/.
# Vendored imports live under base/skills/imported/.
VENDORED_PREFIX = "base/skills/imported/"


def _skill_roots(repo_root: Path) -> list[Path]:
    """v0.11: walk base/ + overlays/team/ skill subtrees (matches the
    PlaybookContent.load scope=["team"] union)."""
    return [
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ]


# First-party skills explicitly exempted from the warn threshold. Each
# entry pairs the relative SKILL.md path with the documented reason.
# Goal: every entry justifies why progressive disclosure would *worsen*
# the skill rather than improve it. Reviewers should challenge entries
# whose justification reads as "I did not want to split it"; legitimate
# entries describe a structural reason.
LONGFORM_EXCEPTIONS: dict[str, str] = {
    "base/skills/research/agent-repo-briefing/SKILL.md": (
        "end-to-end first-day repo briefing for a research collaborator; "
        "the checklist + worked output need to live together to be a "
        "single-pass deliverable."
    ),
    "base/skills/research/data-profiling/SKILL.md": (
        "data profiling workflow with multi-stage decision tree; the "
        "branches reference each other and lose meaning when split into "
        "separate references."
    ),
    "base/skills/research/hypothesis-design/SKILL.md": (
        "hypothesis-design template plus worked example and pitfalls "
        "table; each section grounds the next."
    ),
    "base/skills/research/literature-synthesis/SKILL.md": (
        "literature-synthesis multi-pass workflow with embedded prompt "
        "snippets and rubric; cross-references would explode the page "
        "count if split."
    ),
    "base/skills/research/notebook-to-production/SKILL.md": (
        "step-by-step productionalization walkthrough with code diffs "
        "before/after each transformation; reference splits would make "
        "the diffs less useful."
    ),
    "base/skills/research/rag-eval-method/SKILL.md": (
        "RAG eval methodology with explicit metric formulas, dataset "
        "construction recipe, and worked numerical example; splitting "
        "loses the formula-to-example link."
    ),
    "base/skills/research/statistical-analysis/SKILL.md": (
        "statistical-analysis decision tree across test families with "
        "in-line worked examples; the tree is the skill."
    ),
}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    roots = [r for r in _skill_roots(repo_root) if r.is_dir()]
    if not roots:
        print(
            "  no skill roots found at base/skills/ or overlays/team/skills/; nothing to check"
        )
        return 0

    warnings: list[str] = []
    exemptions_seen: list[str] = []
    vendored_warns: list[str] = []
    errors: list[str] = []
    checked = 0

    skill_paths: list = []
    for root in roots:
        skill_paths.extend(sorted(root.rglob("SKILL.md")))
    for skill_md in skill_paths:
        checked += 1
        rel = str(skill_md.relative_to(repo_root))
        lines = skill_md.read_text(encoding="utf-8").splitlines()
        n = len(lines)
        is_vendored = rel.startswith(VENDORED_PREFIX)
        is_longform = rel in LONGFORM_EXCEPTIONS
        if n >= BLOCK_LINES and not is_vendored:
            errors.append(
                f"{rel}: {n} lines (BLOCK >={BLOCK_LINES}) split into trigger + references/ + scripts/"
            )
            continue
        if n < WARN_LINES:
            continue
        if is_vendored:
            vendored_warns.append(f"{rel}: {n} lines [vendored]")
            continue
        if is_longform:
            exemptions_seen.append(f"{rel}: {n} lines [longform-exception]")
            continue
        warnings.append(
            f"{rel}: {n} lines (>={WARN_LINES}) consider progressive disclosure"
        )

    if vendored_warns:
        print(
            f"\nSize check: {len(vendored_warns)} vendored skill(s) over the soft line (informational)"
        )
        for w in vendored_warns:
            print(f"  i  {w}")

    if exemptions_seen:
        print(
            f"\nSize check: {len(exemptions_seen)} first-party longform exemption(s)"
            f" (documented in scripts/size_check.py LONGFORM_EXCEPTIONS)"
        )
        for w in exemptions_seen:
            print(f"  i  {w}")

    if warnings:
        print(f"\nSize check: {len(warnings)} warning(s)")
        for w in warnings:
            print(f"  !  {w}")

    if errors:
        print(f"\nSize check: {len(errors)} error(s) (BLOCKING)")
        for e in errors:
            print(f"  x  {e}")
        return 1

    if not warnings:
        msg = f"size check passed ({checked} skill(s) checked"
        if vendored_warns or exemptions_seen:
            msg += (
                f"; {len(vendored_warns)} vendored + "
                f"{len(exemptions_seen)} longform-exempted, see above"
            )
        msg += ")"
        print(f"  ok  {msg}")
    else:
        print(
            f"  ok  size check passed ({checked} skill(s), {len(warnings)} "
            f"above the {WARN_LINES} soft line)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
