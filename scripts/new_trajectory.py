#!/usr/bin/env python3
"""
Scaffold a new trajectory file at base/trajectories/<skill>/<scenario>.yaml.

Usage:
  python3 scripts/new_trajectory.py --skill <name> --scenario <slug>

Or via make:
  make new TRAJECTORY=<skill>:<scenario>

The scaffold writes a trajectory with 5 placeholder phrasings, a single
example assertion, and a TODO-marked LLM-judge rubric. Authors fill in
the real values before committing. The trajectory linter (ADR-0043) gates
the result on shape; the harness (Phase 1) replays it across adapters.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path


TEMPLATE = """---
name: {skill}/{scenario}
description: TODO one-line description of what this trajectory verifies.
skill: {skill}
scenario: {scenario}
version: 0.1.0
owner: {owner}
last_reviewed: {today}
tags: []
adapter_scope: [claude-code]
model_pinned: TODO-model-id
authoring_mode: recorded
---

input:
  phrasings:
    - "TODO first phrasing"
    - "TODO second phrasing"
    - "TODO third phrasing"
    - "TODO fourth phrasing"
    - "TODO fifth phrasing"
  variant_strategy: parallel

assertions:
  - first_skill_loaded: {skill}

llm_judge:
  threshold: 0.7
  rubric: |
    TODO Score the trajectory on:
    1. Did the agent do the right first thing?
    2. Did the agent produce the expected artifact?
    3. Did the agent avoid forbidden tools?
  model: claude-sonnet-4-6
"""


def _skill_directory(repo_root: Path, skill: str) -> Path | None:
    """Return the first base/skills/<category>/<skill>/ that contains
    SKILL.md, or None if no such directory exists.
    """
    base_skills = repo_root / "base" / "skills"
    if not base_skills.is_dir():
        return None
    for category_dir in base_skills.iterdir():
        if not category_dir.is_dir():
            continue
        candidate = category_dir / skill
        if (candidate / "SKILL.md").exists():
            return candidate
    return None


def main(
    skill: str | None = None,
    scenario: str | None = None,
    owner: str | None = None,
    repo_root: Path | None = None,
) -> int:
    """Programmatic entry; also wraps argparse for CLI use."""
    if skill is None or scenario is None:
        parser = argparse.ArgumentParser(description="Scaffold a new trajectory")
        parser.add_argument("--skill", required=True, help="Skill slug (must exist)")
        parser.add_argument(
            "--scenario", required=True, help="Scenario slug (kebab-case, e.g. happy-path)"
        )
        parser.add_argument(
            "--owner",
            default=os.environ.get("USER", "unknown"),
            help="Trajectory owner (default: $USER)",
        )
        args = parser.parse_args()
        skill = args.skill
        scenario = args.scenario
        owner = args.owner

    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    if owner is None:
        owner = os.environ.get("USER", "unknown")

    # After the argparse + defaults pass above, these are guaranteed non-None;
    # narrow the types for pyright so downstream Path arithmetic typechecks.
    assert skill is not None and scenario is not None
    skill_str: str = skill
    scenario_str: str = scenario

    if not _skill_directory(repo_root, skill_str):
        print(
            f"  error  skill '{skill_str}' not found under base/skills/<category>/{skill_str}/. "
            f"Create the skill first via `make new SKILL={skill_str}`."
        )
        return 1

    target_dir = repo_root / "base" / "trajectories" / skill_str
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{scenario_str}.yaml"
    if target.exists():
        print(f"  error  trajectory already exists: {target.relative_to(repo_root)}")
        return 1

    body = TEMPLATE.format(
        skill=skill_str,
        scenario=scenario_str,
        owner=owner,
        today=date.today().isoformat(),
    )
    target.write_text(body, encoding="utf-8")
    print(f"  ok  scaffolded {target.relative_to(repo_root)}")
    print("      Replace TODO markers, then `make check` to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
