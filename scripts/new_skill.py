#!/usr/bin/env python3
"""
Scaffold a new skill: creates skills/<category>/<name>/SKILL.md with frontmatter.

Usage:
  python3 scripts/new_skill.py --name my-workflow --category engineering

Or via make:
  make new SKILL=my-workflow CATEGORY=engineering
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

VALID_CATEGORIES = {"engineering", "productivity", "observability", "meta"}


TEMPLATE = """---
name: {name}
description: Use when ... (one sentence, third-person, starts with the trigger condition).
version: 0.1.0
owner: {owner}
last_reviewed: {today}
tags: []
scope: [any]
---

# {title}

(One paragraph: what this skill does, when to use it, when NOT to use it.)

## Steps

1. (First step)
2. (Second step)
3. (Continue ...)

## Output shape

(What does this skill produce? Show an example if useful.)

## When NOT to use this skill

- (Out-of-scope case 1)
- (Out-of-scope case 2)
"""


def slug_to_title(slug: str) -> str:
    return " ".join(word.capitalize() for word in slug.split("-"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new skill")
    parser.add_argument("--name", required=True, help="Skill slug (kebab-case)")
    parser.add_argument(
        "--category",
        default="engineering",
        choices=sorted(VALID_CATEGORIES),
        help="Category (default: engineering)",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("USER", "unknown"),
        help="Skill owner (default: $USER)",
    )
    parser.add_argument(
        "--scope",
        default="base",
        choices=("base", "team"),
        help=(
            "v0.11 (ADR-0040): which tree to scaffold under. 'base' = "
            "base/skills/<cat>/<name>/ (generic, default). 'team' = "
            "overlays/<name>/skills/<cat>/<name>/ (team-specific). See "
            "CONTRIBUTING.md 'Choosing base vs overlays/<name>' for the policy."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): route the scaffold under base/skills/ or
    # overlays/<name>/skills/ per --scope. Old skills/<cat>/<name>/ path
    # is no longer walked by the loader.
    if args.scope == "team":
        skill_dir = repo_root / "overlays" / "team" / "skills" / args.category / args.name
    else:
        skill_dir = repo_root / "base" / "skills" / args.category / args.name
    skill_md = skill_dir / "SKILL.md"

    if skill_md.exists():
        print(f"  error  skill already exists: {skill_md.relative_to(repo_root)}")
        return 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md.write_text(
        TEMPLATE.format(
            name=args.name,
            owner=args.owner,
            today=date.today().isoformat(),
            title=slug_to_title(args.name),
        ),
        encoding="utf-8",
    )
    print(f"  ok  scaffolded {skill_md.relative_to(repo_root)}")
    print("      Edit it, fill in description/steps, then `make check` to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
