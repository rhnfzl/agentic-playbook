#!/usr/bin/env python3
"""Per-trajectory verify (Phase 1 task 5).

Lightweight inner-loop tool authors use during development:

    make verify-trajectory SKILL=<name> SCENARIO=<name>

Runs ONE trajectory against Claude Code (Phase 2) or against a fixture
trace file (Phase 1; the `--fixture` flag). Phase 1 default behavior is
intentionally fixture-only: live Claude Code spawning is Phase 2's job.

When the live runner ships:

    make verify-trajectory SKILL=demo SCENARIO=happy-path
      -> spawn Claude Code with the first phrasing, capture the OTel
         trace, evaluate DSL assertions, report.

Today (Phase 1):

    make verify-trajectory SKILL=demo SCENARIO=happy-path FIXTURE=trace.jsonl
      -> parse the JSONL through the Claude Code shim, evaluate DSL
         against the resulting TraceRecord, report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters._loader import PlaybookContent  # noqa: E402
from adapters.claude_code_trace import parse_otel_jsonl  # noqa: E402
from trajectory_matcher import evaluate_assertions  # noqa: E402


def main(
    skill: str | None = None,
    scenario: str | None = None,
    fixture: Path | None = None,
    repo_root: Path | None = None,
    phrasing: str | None = None,
) -> int:
    if skill is None or scenario is None:
        parser = argparse.ArgumentParser(
            description="Verify ONE trajectory against Claude Code (or a fixture trace)."
        )
        parser.add_argument("--skill", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument(
            "--fixture",
            type=Path,
            default=None,
            help="Path to a JSONL trace fixture; bypasses live Claude Code "
            "(Phase 2 will make this optional once live spawning lands).",
        )
        parser.add_argument(
            "--phrasing",
            default=None,
            help="Override the prompt used to label the trace (default: "
            "the first entry in the trajectory's phrasings list). Useful "
            "when a fixture was captured against a non-default phrasing.",
        )
        args = parser.parse_args()
        skill = args.skill
        scenario = args.scenario
        fixture = args.fixture
        phrasing = args.phrasing

    if repo_root is None:
        repo_root = REPO_ROOT_DEFAULT

    content = PlaybookContent.load(repo_root)
    matching = [
        t for t in content.trajectories
        if t.skill == skill and t.scenario == scenario
    ]
    if not matching:
        print(
            f"  error  trajectory '{skill}/{scenario}' not found under "
            f"base/trajectories/{skill}/{scenario}.yaml",
            file=sys.stderr,
        )
        return 1
    traj = matching[0]

    if fixture is None:
        print(
            "  error  --fixture is required in Phase 1 (live Claude Code "
            "spawning lands in Phase 2). Provide a captured trace JSONL.",
            file=sys.stderr,
        )
        return 1

    if not fixture.is_file():
        print(f"  error  fixture file not found: {fixture}", file=sys.stderr)
        return 1

    # Use the first phrasing as the prompt unless the author overrode
    # via --phrasing. Verify is single-shot, not the full matrix.
    if phrasing is not None:
        prompt = phrasing
    elif traj.input_phrasings:
        prompt = traj.input_phrasings[0]
    else:
        prompt = ""
    trace = parse_otel_jsonl(fixture, session_id="verify", prompt=prompt)
    result = evaluate_assertions(traj.assertions, trace)

    if result.passed:
        print(
            f"  ok  trajectory '{skill}/{scenario}' PASSED against fixture "
            f"({fixture.name}): {len(traj.assertions)} assertion(s) satisfied."
        )
        return 0

    print(
        f"  fail  trajectory '{skill}/{scenario}' FAILED against fixture "
        f"({fixture.name}):",
        file=sys.stderr,
    )
    for failure in result.failures:
        print(f"    - {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
