#!/usr/bin/env python3
"""Judge calibration check (Phase 2C-β, ADR-0046).

Runs a trajectory's LLM-judge rubric N times against a fixed trace and
reports per-rubric score variance. A rubric whose scores swing by more
than `noise_threshold` between consecutive temperature=0 runs is too
subjective for the hybrid match contract; the report flags it so the
author can tighten the rubric (or drop the judge half for that
trajectory).

Usage:

    make trajectory-calibrate SKILL=<name> SCENARIO=<name>
    python3 scripts/trajectory_calibrate.py \\
        --skill demo --scenario happy-path --runs 5 [--json]

In production the rubric is graded against a real fixture trace (from
`base/trajectories/<skill>/fixtures/<scenario>-pass.jsonl`). For Phase
2C-β the tool accepts an injected `trace_provider` and `client_factory`
so tests can run without a real LLM. The CLI default reads the canary
fixture and instantiates `HttpAnthropicJudgeClient` from
`ANTHROPIC_API_KEY`.

Out of scope: cross-model calibration (running the same rubric against
different judge models). The ADR-0046 reject-if criterion is variance
at a single temperature, not cross-model agreement.
"""

from __future__ import annotations

import argparse
import json as _json
import statistics
import sys
from pathlib import Path
from typing import Callable, NamedTuple

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters._loader import PlaybookContent  # noqa: E402
from trajectory_judge import JudgeClient, evaluate_judge  # noqa: E402


_DEFAULT_NOISE_THRESHOLD = 0.1
_DEFAULT_RUNS = 5


class CalibrationReport(NamedTuple):
    """Per-trajectory calibration result.

    scores         -- the N raw scores, in invocation order.
    variance       -- max(scores) - min(scores); simple range metric
                      that matches the ADR's "0.1 between consecutive
                      runs" language better than statistical variance.
    is_noisy       -- variance > threshold; the report's go/no-go bit.
    min/max/median -- distribution snapshot for the author's eye.
    """

    skill: str
    scenario: str
    runs: int
    scores: list[float]
    variance: float
    is_noisy: bool
    noise_threshold: float
    min_score: float
    max_score: float
    median_score: float
    model: str


def calibrate_trajectory(
    trajectory,  # type: ignore[no-untyped-def]
    trace,  # type: ignore[no-untyped-def]
    client: JudgeClient,
    runs: int = _DEFAULT_RUNS,
    noise_threshold: float = _DEFAULT_NOISE_THRESHOLD,
) -> CalibrationReport:
    """Run the rubric `runs` times against `trace`; return a report."""
    if runs < 2:
        raise ValueError(
            f"calibration requires runs >= 2 (got {runs}); a single "
            f"score has no variance signal"
        )
    scores: list[float] = []
    model = "unknown"
    for _ in range(runs):
        result = evaluate_judge(trajectory, trace, client)
        scores.append(result.score)
        if result.model:
            model = result.model
    variance = max(scores) - min(scores)
    return CalibrationReport(
        skill=trajectory.skill,
        scenario=trajectory.scenario,
        runs=runs,
        scores=scores,
        variance=variance,
        is_noisy=variance > noise_threshold,
        noise_threshold=noise_threshold,
        min_score=min(scores),
        max_score=max(scores),
        median_score=statistics.median(scores),
        model=model,
    )


def _print_report_human(report: CalibrationReport) -> None:
    print()
    print(f"Calibration: {report.skill}/{report.scenario}")
    print(f"  runs:             {report.runs}")
    print(f"  scores:           {[round(s, 3) for s in report.scores]}")
    print(f"  variance (range): {report.variance:.3f}")
    print(f"  threshold:        {report.noise_threshold}")
    print(
        f"  min / median / max: "
        f"{report.min_score:.3f} / {report.median_score:.3f} / "
        f"{report.max_score:.3f}"
    )
    print(f"  model:            {report.model}")
    if report.is_noisy:
        print(
            f"  NOISY: variance exceeds threshold. Per ADR-0046, "
            f"tighten the rubric or drop the LLM-judge half."
        )
    else:
        print(f"  ok  rubric within calibration threshold")
    print()


def main(
    repo_root: Path | None = None,
    skill: str | None = None,
    scenario: str | None = None,
    runs: int = _DEFAULT_RUNS,
    noise_threshold: float = _DEFAULT_NOISE_THRESHOLD,
    json_output: bool = False,
    client_factory: Callable[[], JudgeClient] | None = None,
    trace_provider: Callable | None = None,  # type: ignore[type-arg]
) -> int:
    if skill is None or scenario is None:
        parser = argparse.ArgumentParser(
            description="Calibrate a trajectory's LLM-judge rubric."
        )
        parser.add_argument("--skill", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument("--runs", type=int, default=_DEFAULT_RUNS)
        parser.add_argument(
            "--noise-threshold", type=float, default=_DEFAULT_NOISE_THRESHOLD,
        )
        parser.add_argument("--json", action="store_true")
        args = parser.parse_args()
        skill = args.skill
        scenario = args.scenario
        runs = args.runs
        noise_threshold = args.noise_threshold
        json_output = args.json

    if repo_root is None:
        repo_root = REPO_ROOT_DEFAULT

    content = PlaybookContent.load(repo_root)
    matching = [
        t for t in content.trajectories
        if t.skill == skill and t.scenario == scenario
    ]
    if not matching:
        print(
            f"  error  trajectory '{skill}/{scenario}' not found",
            file=sys.stderr,
        )
        return 1
    traj = matching[0]

    if trace_provider is None:
        # After the argparse path above, skill/scenario are guaranteed
        # non-None. Narrow for pyright.
        assert skill is not None and scenario is not None
        fixture_path = (
            repo_root / "base" / "trajectories" / skill / "fixtures"
            / f"{scenario}-pass.jsonl"
        )
        if not fixture_path.is_file():
            print(
                f"  error  no fixture at {fixture_path}; pass "
                f"trace_provider= for non-default sources",
                file=sys.stderr,
            )
            return 1
        from adapters.claude_code_trace import parse_otel_jsonl

        prompt = traj.input_phrasings[0] if traj.input_phrasings else ""
        trace = parse_otel_jsonl(
            fixture_path, session_id="calibrate", prompt=prompt,
        )
    else:
        trace = trace_provider(traj)

    if client_factory is None:
        from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

        try:
            client: JudgeClient = HttpAnthropicJudgeClient()
        except ValueError as exc:
            print(f"  error  cannot create judge client: {exc}", file=sys.stderr)
            return 1
    else:
        client = client_factory()

    report = calibrate_trajectory(
        trajectory=traj,
        trace=trace,
        client=client,
        runs=runs,
        noise_threshold=noise_threshold,
    )

    if json_output:
        print(_json.dumps(report._asdict(), indent=2))
    else:
        _print_report_human(report)
    return 1 if report.is_noisy else 0


if __name__ == "__main__":
    sys.exit(main())
