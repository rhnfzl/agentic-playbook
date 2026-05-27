#!/usr/bin/env python3
"""
Warn on skills with last_reviewed > 90 days; block at > 180 days.

Inspired by Packmind's drift-detection research. The premise: rules and
skills decay silently without an explicit review cadence. Forcing a
last_reviewed date in frontmatter and checking it in CI makes decay visible.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

NOTICE_DAYS = 60  # Q13 lock: early-warning band before WARN_DAYS
WARN_DAYS = 90
BLOCK_DAYS = 180


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): skills moved to base/ + overlays/<name>/.
    skill_roots = [
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ]
    skill_roots = [r for r in skill_roots if r.is_dir()]
    if not skill_roots:
        print("  no skill roots found at base/skills/ or overlays/<name>/skills/; nothing to check")
        return 0

    today = date.today()
    notices: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    checked = 0

    skill_paths: list = []
    for root in skill_roots:
        skill_paths.extend(sorted(root.rglob("SKILL.md")))
    for skill_md in skill_paths:
        checked += 1
        rel = skill_md.relative_to(repo_root)
        content = skill_md.read_text(encoding="utf-8")

        match = re.search(r"last_reviewed:\s*(\d{4}-\d{2}-\d{2})", content)
        if not match:
            errors.append(f"{rel}: no last_reviewed field")
            continue

        try:
            last = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{rel}: invalid last_reviewed date format")
            continue

        age = (today - last).days

        if age >= BLOCK_DAYS:
            errors.append(f"{rel}: last_reviewed {age}d ago (>{BLOCK_DAYS}d, BLOCKING)")
        elif age >= WARN_DAYS:
            warnings.append(f"{rel}: last_reviewed {age}d ago (>{WARN_DAYS}d)")
        elif age >= NOTICE_DAYS:
            notices.append(
                f"{rel}: last_reviewed {age}d ago ({NOTICE_DAYS}-{WARN_DAYS}d band, refresh soon)"
            )

    if notices:
        print(
            f"\nDecay check: {len(notices)} notice(s) in {NOTICE_DAYS}-{WARN_DAYS}d band"
        )
        for n in notices:
            print(f"  .  {n}")

    if warnings:
        print(f"\nDecay check: {len(warnings)} warning(s)")
        for w in warnings:
            print(f"  !  {w}")

    if errors:
        print(f"\nDecay check: {len(errors)} error(s)")
        for e in errors:
            print(f"  x  {e}")
        return 1

    if not warnings and not notices:
        print(f"  ok  all {checked} skill(s) reviewed within {NOTICE_DAYS} days")
    elif not warnings:
        print(
            f"  ok  all {checked} skill(s) reviewed within {WARN_DAYS} days "
            f"({len(notices)} approaching the {WARN_DAYS}d warn line)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
