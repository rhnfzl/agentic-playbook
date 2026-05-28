#!/usr/bin/env python3
"""Judge calibration check (Phase 2C-beta, ADR-0046).

Runs a trajectory's LLM-judge rubric N times against a fixed trace and
reports the score range (`max(scores) - min(scores)`) across runs. A
rubric whose scores swing by more than `noise_threshold` between
temperature=0 runs is too subjective for the hybrid match contract;
the report flags it so the author can tighten the rubric (or drop the
judge half for that trajectory).

Judge infra errors (HTTP 429, parse failures, timeouts) are surfaced
separately from rubric variance. A synthetic `score=0.0` from a
`JudgeResult(is_infra_error=True)` would otherwise pollute the range
and mark a stable rubric as noisy (review-fold P2 #5). Infra-errored
runs are excluded from the score set, counted independently, and
become their own non-zero exit reason so the operator retries instead
of treating the rubric as broken.

Usage:

    make trajectory-calibrate SKILL=<name> SCENARIO=<name>
    python3 scripts/trajectory_calibrate.py \\
        --skill demo --scenario happy-path --runs 5 [--json]

In production the rubric is graded against a real fixture trace (from
`base/trajectories/<skill>/fixtures/<scenario>-pass.jsonl`). The tool
accepts an injected `trace_provider` and `client_factory` so tests can
run without a real LLM. The CLI default reads the canary fixture and
instantiates `HttpAnthropicJudgeClient` from `ANTHROPIC_API_KEY`.

Out of scope: cross-model calibration (running the same rubric against
different judge models). The ADR-0046 reject-if criterion is range at
a single temperature, not cross-model agreement.
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

    scores            -- the successful raw scores, in invocation order.
                         Excludes infra-error runs so a flaky judge
                         endpoint cannot poison the range (review-fold
                         P2 #5).
    score_range       -- max(scores) - min(scores); the metric the ADR
                         actually describes ("noise above 0.1 between
                         consecutive runs"). Renamed from `variance`
                         which was misleading because the value is a
                         range, not statistical variance (review-fold
                         thermo-nuclear nice-to-have).
    is_noisy          -- score_range > threshold AND at least one
                         successful run happened. A run with all-infra
                         errors is `is_noisy=False` but
                         `usable_signal=False`; the operator should
                         retry rather than treat the rubric as broken.
    usable_signal     -- True iff `scores` has at least 2 entries (so
                         range is meaningful). When False, treat the
                         report as "couldn't measure" rather than "the
                         rubric is fine."
    requested_runs    -- the N the caller asked for.
    successful_runs   -- len(scores); how many runs returned a real
                         judgement.
    infra_errors      -- count of runs that returned
                         `JudgeResult(is_infra_error=True)`.
    min/max/median    -- distribution snapshot for the author's eye.
    """

    skill: str
    scenario: str
    requested_runs: int
    successful_runs: int
    infra_errors: int
    scores: list[float]
    score_range: float
    is_noisy: bool
    usable_signal: bool
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
    """Run the rubric `runs` times against `trace`; return a report.

    Calls `evaluate_judge` `runs` times. Each call returns a
    `JudgeResult`; if `is_infra_error=True` (HTTP failure, parse
    failure, refusal phrase) the synthetic 0.0 score is NOT folded
    into the variance set. That avoids the review-fold P2 #5 failure
    mode where one 429 retroactively marks an otherwise stable rubric
    as noisy.
    """
    if runs < 2:
        raise ValueError(
            f"calibration requires runs >= 2 (got {runs}); a single "
            f"score has no range signal"
        )
    scores: list[float] = []
    infra_errors = 0
    model = "unknown"
    for _ in range(runs):
        result = evaluate_judge(trajectory, trace, client)
        if result.model:
            model = result.model
        if result.is_infra_error:
            infra_errors += 1
            continue
        scores.append(result.score)

    usable_signal = len(scores) >= 2
    if usable_signal:
        score_range = max(scores) - min(scores)
        min_score = min(scores)
        max_score = max(scores)
        median_score = statistics.median(scores)
        is_noisy = score_range > noise_threshold
    else:
        # No (or one) successful run. Range is undefined; defer to the
        # operator. is_noisy=False so the report does not blame the
        # rubric for what is really a transport problem.
        score_range = 0.0
        min_score = 0.0
        max_score = 0.0
        median_score = 0.0
        is_noisy = False

    return CalibrationReport(
        skill=trajectory.skill,
        scenario=trajectory.scenario,
        requested_runs=runs,
        successful_runs=len(scores),
        infra_errors=infra_errors,
        scores=scores,
        score_range=score_range,
        is_noisy=is_noisy,
        usable_signal=usable_signal,
        noise_threshold=noise_threshold,
        min_score=min_score,
        max_score=max_score,
        median_score=median_score,
        model=model,
    )


def _print_report_human(report: CalibrationReport) -> None:
    print()
    print(f"Calibration: {report.skill}/{report.scenario}")
    print(f"  requested runs:   {report.requested_runs}")
    print(f"  successful runs:  {report.successful_runs}")
    if report.infra_errors:
        print(f"  infra errors:     {report.infra_errors}")
    print(f"  scores:           {[round(s, 3) for s in report.scores]}")
    print(f"  score range:      {report.score_range:.3f}")
    print(f"  threshold:        {report.noise_threshold}")
    print(
        f"  min / median / max: "
        f"{report.min_score:.3f} / {report.median_score:.3f} / "
        f"{report.max_score:.3f}"
    )
    print(f"  model:            {report.model}")
    if not report.usable_signal:
        print(
            f"  UNUSABLE: only {report.successful_runs} successful "
            f"run(s) out of {report.requested_runs}. Retry the "
            f"calibration before treating the rubric as broken."
        )
    elif report.is_noisy:
        print(
            f"  NOISY: score range exceeds threshold. Per ADR-0046, "
            f"tighten the rubric or drop the LLM-judge half."
        )
    elif report.infra_errors:
        print(
            f"  ok  rubric within threshold, but {report.infra_errors} "
            f"run(s) failed at the transport layer; retry to confirm."
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
    # Exit 0 only when the rubric is within threshold AND every run
    # produced a real score. Infra errors are surfaced as a non-zero
    # exit so the operator knows to retry rather than treating the
    # rubric as confirmed.
    if not report.usable_signal:
        return 1
    if report.is_noisy:
        return 1
    if report.infra_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
