#!/usr/bin/env python3
"""Trajectory coverage ratio (ADR-0044 reject-if metric).

Prints (trajectory count) / (skill count) plus the adapter_scope
breakdown that the reject-if criteria reference:

  Phase 0 + Phase 1 reject-if criteria (ADR-0044):
    * (trajectories committed / shipped skills) below 0.5 across two
      consecutive releases.
    * More than 50% of trajectories carry `adapter_scope: [claude-code]`
      only (silent opt-out from cross-adapter testing).

Usage:
    make trajectory-coverage-ratio
    python3 scripts/trajectory_coverage.py [--json]
"""

from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters._loader import PlaybookContent  # noqa: E402


def compute_coverage(repo_root: Path) -> dict:
    """Return the coverage summary dict; pure for testing."""
    content = PlaybookContent.load(repo_root)
    skill_count = len(content.skills)
    trajectory_count = len(content.trajectories)
    ratio = (trajectory_count / skill_count) if skill_count else 0.0

    claude_only = sum(
        1 for t in content.trajectories
        if t.adapter_scope == ["claude-code"]
    )
    claude_only_share = (
        (claude_only / trajectory_count) if trajectory_count else 0.0
    )

    return {
        "skill_count": skill_count,
        "trajectory_count": trajectory_count,
        "ratio": round(ratio, 4),
        "target_ratio": 0.5,
        "meets_target": ratio >= 0.5,
        "claude_only_trajectories": claude_only,
        "claude_only_share": round(claude_only_share, 4),
        "claude_only_threshold": 0.5,
        "claude_only_share_above_threshold": claude_only_share > 0.5,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print trajectory coverage ratio (ADR-0044 reject-if metric)."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    args = parser.parse_args()

    summary = compute_coverage(REPO_ROOT_DEFAULT)

    if args.json:
        print(_json.dumps(summary, indent=2))
        return 0

    print()
    print(f"Trajectory coverage (ADR-0044 reject-if metric)")
    print()
    print(f"  Skills shipped:           {summary['skill_count']}")
    print(f"  Trajectories committed:   {summary['trajectory_count']}")
    print(f"  Coverage ratio:           {summary['ratio']}  (target >= {summary['target_ratio']})")
    print(f"  Meets target:             {'yes' if summary['meets_target'] else 'NO'}")
    print()
    print(f"  Claude-only trajectories: {summary['claude_only_trajectories']}")
    print(f"  Claude-only share:        {summary['claude_only_share']}  (alert > {summary['claude_only_threshold']})")
    print(
        f"  Cross-adapter coverage:   "
        f"{'BELOW threshold' if summary['claude_only_share_above_threshold'] else 'ok'}"
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
