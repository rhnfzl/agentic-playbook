#!/usr/bin/env python3
"""Per-trajectory verify (single-trajectory inner-loop tool).

Authors use this during development to re-check ONE trajectory
without paying for a full matrix or a live spawn:

    make verify-trajectory SKILL=<name> SCENARIO=<name> FIXTURE=trace.jsonl

Verify is intentionally fixture-driven. Live Claude Code spawning
lives in `trajectory_harness.py` (Phase 2B) and the recorder
(`trajectory_record.py`); both write JSONL fixtures the author can
then replay through this tool. Keeping verify off the live path makes
the inner loop fast, deterministic, and free of LLM cost.

    -> parse the JSONL through the Claude Code shim
       (`claude_code_trace.parse_otel_jsonl`), evaluate DSL against
       the resulting TraceRecord, and optionally run the LLM judge
       via `--judge` (requires ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters._loader import PlaybookContent  # noqa: E402
from adapters.claude_code_trace import parse_otel_jsonl  # noqa: E402
from trajectory_judge import JudgeClient, evaluate_judge, get_threshold  # noqa: E402
from trajectory_matcher import evaluate_assertions  # noqa: E402


def main(
    skill: str | None = None,
    scenario: str | None = None,
    fixture: Path | None = None,
    repo_root: Path | None = None,
    phrasing: str | None = None,
    judge_client: JudgeClient | None = None,
    judge: bool = False,
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
            help="Path to a JSONL trace fixture. Verify is fixture-only "
            "by design; for live spawn, use `make trajectory-check` (full "
            "matrix) or `make record-trajectory` (capture once, replay here).",
        )
        parser.add_argument(
            "--phrasing",
            default=None,
            help="Override the prompt used to label the trace (default: "
            "the first entry in the trajectory's phrasings list). Useful "
            "when a fixture was captured against a non-default phrasing.",
        )
        parser.add_argument(
            "--judge",
            action="store_true",
            help="After DSL passes, run the LLM judge against the trajectory's "
            "rubric. Requires ANTHROPIC_API_KEY in the environment.",
        )
        args = parser.parse_args()
        skill = args.skill
        scenario = args.scenario
        fixture = args.fixture
        phrasing = args.phrasing
        judge = args.judge

    if repo_root is None:
        repo_root = REPO_ROOT_DEFAULT

    content = PlaybookContent.load(repo_root)
    matching = [
        t for t in content.trajectories if t.skill == skill and t.scenario == scenario
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
            "  error  --fixture is required: verify is fixture-only by "
            "design. Use `make trajectory-check` for live spawn, or "
            "`make record-trajectory` to capture a JSONL first.",
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

    # Hybrid match (ADR-0046): if --judge was requested and DSL passed,
    # run the LLM judge and gate on the trajectory's threshold.
    judge_failure_msg: str | None = None
    if result.passed and judge:
        client = judge_client
        if client is None:
            # Default real client; reads ANTHROPIC_API_KEY.
            from adapters.anthropic_judge_client import (
                HttpAnthropicJudgeClient,
            )

            try:
                client = HttpAnthropicJudgeClient()
            except ValueError as exc:
                print(
                    f"  error  cannot run judge: {exc}",
                    file=sys.stderr,
                )
                return 1
        judge_result = evaluate_judge(traj, trace, client)
        threshold = get_threshold(traj)
        if judge_result.score < threshold:
            prefix = "judge_infra_fail" if judge_result.is_infra_error else "llm_judge"
            judge_failure_msg = (
                f"{prefix}: score {judge_result.score:.2f} below "
                f"threshold {threshold} (reasoning: {judge_result.reasoning})"
            )

    if result.passed and judge_failure_msg is None:
        suffix = " + judge" if judge else ""
        print(
            f"  ok  trajectory '{skill}/{scenario}' PASSED against fixture "
            f"({fixture.name}): {len(traj.assertions)} assertion(s) satisfied{suffix}."
        )
        return 0

    print(
        f"  fail  trajectory '{skill}/{scenario}' FAILED against fixture "
        f"({fixture.name}):",
        file=sys.stderr,
    )
    if judge_failure_msg is not None:
        print(f"    - {judge_failure_msg}", file=sys.stderr)
    for failure in result.failures:
        print(f"    - {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
