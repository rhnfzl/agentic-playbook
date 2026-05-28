#!/usr/bin/env python3
"""Trajectory harness CLI (Phase 1, ADR-0046).

Loads trajectories from the playbook's content, runs each phrasing
against the trace-provider for every adapter in the trajectory's
adapter_scope, and produces a pass/fail matrix.

Phase 1 contract:

  * The harness DOES NOT spawn live agents in this phase. It receives a
    `trace_provider` callable that returns a TraceRecord for each
    (trajectory, phrasing, adapter) tuple. Tests inject a synthetic
    provider; Phase 2 swaps in `run_claude_code_session`.
  * The DSL matcher (scripts/trajectory_matcher.py) evaluates the
    assertions in each trajectory. The LLM judge is Phase 2.
  * Output: a Matrix dataclass that the CLI prints as a table. The
    Matrix shape stays frozen so Phase 2's only job is to plug a real
    trace_provider in.

CLI:

  python3 scripts/trajectory_harness.py [--skill <name>] [--adapter <name>]

  make trajectory-check                 # all trajectories x all adapters
  make trajectory-check SKILL=to-prd    # narrow to one skill
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters._loader import PlaybookContent, Trajectory  # noqa: E402
from adapters.trace_record import KNOWN_TRACE_ADAPTERS, TraceRecord  # noqa: E402
from trajectory_judge import JudgeClient, evaluate_judge, get_threshold  # noqa: E402
from trajectory_matcher import evaluate_assertions  # noqa: E402


TraceProvider = Callable[[Trajectory, str, str], TraceRecord]


@dataclass(frozen=True)
class HarnessConfig:
    """All inputs the harness needs to run.

    `trace_provider` is the seam between Phase 1 (fixture-driven, in-test)
    and Phase 2 (live Claude Code session). The contract is:

      provider(trajectory, phrasing, adapter) -> TraceRecord

    The provider is responsible for spawning the adapter, capturing the
    trace, and returning a TraceRecord. Errors raised by the provider
    propagate so the harness can mark the cell as infra_fail.

    `judge_client` is the Phase 2A addition. When set, the harness runs
    the LLM judge after the DSL matcher passes; both must clear for the
    cell to pass. When None (Phase 1 default), only the DSL runs.

    Phase 2C-α adds defensive infrastructure:

    * `max_provider_calls` caps the live trace_provider invocations per
      run. None = unlimited (preserves Phase 2B behavior). Once the
      budget is exhausted, remaining cells are recorded as skipped with
      `failures=['budget_exhausted: ...']`.
    * `max_judge_calls` caps the LLM judge invocations. Independent
      from the provider budget so a small judge budget can run a full
      DSL pass without LLM-judge spending.
    * `dry_run=True` counts cells without invoking the provider or
      judge. Useful for budgeting before wiring nightly cron.
    * `max_retries` is the number of retries on provider exceptions
      (TimeoutError, RuntimeError). Default 0 keeps the Phase 2B
      behavior of recording the first failure as infra_fail. Sleep
      between retries is `retry_backoff_s * (2 ** attempt)` (zero in
      tests).

    `skill_filter` narrows the run to one skill (or None for all).
    `adapter_filter` narrows to one adapter (or None for all).
    `strict` flips adapter_unavailable into a hard failure.
    """

    repo_root: Path
    trace_provider: TraceProvider
    judge_client: JudgeClient | None = None
    skill_filter: str | None = None
    adapter_filter: str | None = None
    strict: bool = False
    max_provider_calls: int | None = None
    max_judge_calls: int | None = None
    dry_run: bool = False
    max_retries: int = 0
    retry_backoff_s: float = 1.0


@dataclass(frozen=True)
class MatrixCell:
    """One (skill, scenario, phrasing, adapter) result."""

    skill: str
    scenario: str
    phrasing: str
    adapter: str
    passed: bool
    failures: list[str]


@dataclass
class Matrix:
    """Aggregated matrix output. Mutable so the harness can append cells.

    `cells` is at (skill, scenario, phrasing, adapter) granularity.
    `total`/`passed`/`failed` aggregate to TRAJECTORY+ADAPTER granularity:
    one (skill, scenario, adapter) tuple passes only if every phrasing
    in that tuple passed.
    """

    cells: list[MatrixCell] = field(default_factory=list)

    def _trajectory_results(self) -> dict[tuple[str, str, str], bool]:
        by_key: dict[tuple[str, str, str], bool] = {}
        for cell in self.cells:
            k = (cell.skill, cell.scenario, cell.adapter)
            by_key[k] = by_key.get(k, True) and cell.passed
        return by_key

    @property
    def total(self) -> int:
        return len(self._trajectory_results())

    @property
    def passed(self) -> int:
        return sum(1 for v in self._trajectory_results().values() if v)

    @property
    def failed(self) -> int:
        return sum(1 for v in self._trajectory_results().values() if not v)


def _iter_trajectories(
    content: PlaybookContent,
    skill_filter: str | None,
) -> Iterable[Trajectory]:
    for traj in content.trajectories:
        if skill_filter and traj.skill != skill_filter:
            continue
        yield traj


def _call_provider_with_retry(
    provider: TraceProvider,
    trajectory: Trajectory,
    phrasing: str,
    adapter: str,
    *,
    max_retries: int,
    backoff_s: float,
) -> "TraceRecord | Exception":
    """Wrap the provider call in a retry loop. Returns either the
    TraceRecord on success or the FINAL exception after exhausting
    retries.

    Retries on TimeoutError and RuntimeError only — those are the
    classes the ClaudeCodeProvider raises for transient failures
    (timeout, non-zero exit from a crashed `claude`). Other exceptions
    (ValueError on bad adapter, KeyboardInterrupt) propagate
    immediately because retrying them won't help.

    Backoff is exponential: `backoff_s * (2 ** attempt)` where attempt
    is 0-indexed. Tests set backoff_s=0 so they don't slow the suite.
    """
    import time as _time

    attempt = 0
    last_exc: Exception | None = None
    while attempt <= max_retries:
        try:
            return provider(trajectory, phrasing, adapter)
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if attempt < max_retries and backoff_s > 0:
                _time.sleep(backoff_s * (2 ** attempt))
            attempt += 1
        except Exception as exc:
            # Non-retriable: ValueError (bad adapter), etc.
            return exc
    assert last_exc is not None
    return last_exc


# Adapter registry lives in adapters/trace_record.py; reuse the frozenset
# rather than maintain a parallel copy here (third-review finding:
# triplicate registry meant Phase 3 shims would silently drift).


def run_harness(cfg: HarnessConfig) -> Matrix:
    """Execute the matrix and return the aggregated result.

    Raises ValueError if filters narrow the run to zero cells. A typo
    like ADAPTER=claud-code (note the missing `e`) would otherwise exit
    green with zero cells, which is misleading CI output (codex review
    finding).
    """
    content = PlaybookContent.load(cfg.repo_root)
    matrix = Matrix()

    if cfg.strict:
        # Phase 1 has no live adapters and therefore no `adapter_unavailable`
        # to escalate to a hard failure. Make the no-op visible so a CI
        # configuration that sets STRICT=1 expecting enforcement gets a
        # clear advisory rather than a silent green pass.
        import warnings as _warnings
        _warnings.warn(
            "strict mode is a Phase 2 feature; no live adapters to flag "
            "as unavailable. STRICT=1 has no effect in Phase 1.",
            UserWarning,
            stacklevel=2,
        )

    if cfg.adapter_filter and cfg.adapter_filter not in KNOWN_TRACE_ADAPTERS:
        raise ValueError(
            f"adapter filter '{cfg.adapter_filter}' is not in the known "
            f"adapter set {sorted(KNOWN_TRACE_ADAPTERS)}; check for a "
            f"typo or add the adapter to KNOWN_TRACE_ADAPTERS."
        )

    candidate_trajectories = list(_iter_trajectories(content, cfg.skill_filter))
    if cfg.skill_filter and not candidate_trajectories:
        raise ValueError(
            f"skill filter '{cfg.skill_filter}' matched no trajectories; "
            f"available skills: {sorted({t.skill for t in content.trajectories})}"
        )

    # Pre-flight: if the adapter filter is valid but no trajectory has it
    # in adapter_scope, the loop below produces zero cells and matrix.failed
    # == 0 falsely reports success (third-review P2 finding). Fail loud.
    if cfg.adapter_filter:
        scopes_with_adapter = [
            t for t in candidate_trajectories
            if cfg.adapter_filter in t.adapter_scope
        ]
        if not scopes_with_adapter:
            adapter_options = sorted({
                a for t in candidate_trajectories for a in t.adapter_scope
            })
            raise ValueError(
                f"adapter filter '{cfg.adapter_filter}' is valid but no "
                f"trajectory in scope declares it in adapter_scope; "
                f"trajectories use these adapters: {adapter_options}"
            )

    provider_calls = 0
    judge_calls = 0

    for traj in candidate_trajectories:
        adapters = traj.adapter_scope
        if cfg.adapter_filter:
            adapters = [a for a in adapters if a == cfg.adapter_filter]

        for adapter in adapters:
            for phrasing in traj.input_phrasings:
                # Dry-run: never invoke the provider or judge; record
                # every cell as a planned-skip so the matrix shows the
                # full intended workload.
                if cfg.dry_run:
                    matrix.cells.append(
                        MatrixCell(
                            skill=traj.skill,
                            scenario=traj.scenario,
                            phrasing=phrasing,
                            adapter=adapter,
                            passed=False,
                            failures=["dry_run: cell counted, not executed"],
                        )
                    )
                    continue

                # Cost ceiling on provider calls. Cells past the cap are
                # recorded as budget-exhausted so the matrix shows what
                # was skipped (rather than silently shrinking).
                if (
                    cfg.max_provider_calls is not None
                    and provider_calls >= cfg.max_provider_calls
                ):
                    matrix.cells.append(
                        MatrixCell(
                            skill=traj.skill,
                            scenario=traj.scenario,
                            phrasing=phrasing,
                            adapter=adapter,
                            passed=False,
                            failures=[
                                f"budget_exhausted: max_provider_calls="
                                f"{cfg.max_provider_calls} reached"
                            ],
                        )
                    )
                    continue

                provider_calls += 1
                trace_or_exc = _call_provider_with_retry(
                    cfg.trace_provider, traj, phrasing, adapter,
                    max_retries=cfg.max_retries,
                    backoff_s=cfg.retry_backoff_s,
                )
                if isinstance(trace_or_exc, Exception):
                    exc = trace_or_exc
                    matrix.cells.append(
                        MatrixCell(
                            skill=traj.skill,
                            scenario=traj.scenario,
                            phrasing=phrasing,
                            adapter=adapter,
                            passed=False,
                            failures=[
                                f"infra_fail: trace_provider raised "
                                f"{type(exc).__name__}: {exc}"
                            ],
                        )
                    )
                    continue
                trace = trace_or_exc

                result = evaluate_assertions(traj.assertions, trace)
                failures = list(result.failures)
                passed = result.passed

                # Phase 2A: if DSL passed AND a judge_client is wired,
                # run the LLM judge and gate on the trajectory threshold.
                # DSL failures short-circuit the judge to save cost.
                if passed and cfg.judge_client is not None:
                    if (
                        cfg.max_judge_calls is not None
                        and judge_calls >= cfg.max_judge_calls
                    ):
                        failures.append(
                            f"judge_budget_exhausted: max_judge_calls="
                            f"{cfg.max_judge_calls}; treating cell as DSL-only pass"
                        )
                    else:
                        judge_calls += 1
                        judge_result = evaluate_judge(
                            traj, trace, cfg.judge_client,
                        )
                        threshold = get_threshold(traj)
                        if judge_result.score < threshold:
                            passed = False
                            # Distinguish infra failures from quality
                            # failures so operators reading the matrix
                            # can route a 429 to "retry overnight" and a
                            # quality miss to "regression to investigate."
                            prefix = (
                                "judge_infra_fail"
                                if judge_result.is_infra_error
                                else "llm_judge"
                            )
                            failures.append(
                                f"{prefix}: score {judge_result.score:.2f} "
                                f"below threshold {threshold} "
                                f"(reasoning: {judge_result.reasoning})"
                            )

                matrix.cells.append(
                    MatrixCell(
                        skill=traj.skill,
                        scenario=traj.scenario,
                        phrasing=phrasing,
                        adapter=adapter,
                        passed=passed,
                        failures=failures,
                    )
                )

    return matrix


def print_summary(matrix: Matrix) -> None:
    """CI-friendly stdout summary. One header row, one row per (skill,
    scenario, adapter) showing pass count over phrasing count."""
    by_key: dict[tuple[str, str, str], tuple[int, int, list[str]]] = {}
    for cell in matrix.cells:
        k = (cell.skill, cell.scenario, cell.adapter)
        passed, total, failures = by_key.get(k, (0, 0, []))
        by_key[k] = (
            passed + (1 if cell.passed else 0),
            total + 1,
            failures + (cell.failures if not cell.passed else []),
        )

    print()
    print(
        f"Trajectory matrix ({matrix.total} cells; "
        f"{matrix.passed} pass, {matrix.failed} fail)"
    )
    print()
    print(f"  {'skill':<24} {'scenario':<18} {'adapter':<14} result")
    print("  " + "-" * 70)
    for (skill, scenario, adapter), (passed, total, _failures) in sorted(by_key.items()):
        verdict = "PASS" if passed == total else f"FAIL ({passed}/{total})"
        print(f"  {skill:<24} {scenario:<18} {adapter:<14} {verdict}")

    if matrix.failed:
        # Codex review-round-4 fix: failure details route to stderr so the
        # stdout/stderr contract holds. The matrix table itself stays on
        # stdout (it's the normal output even when some cells fail; the
        # exit code is the signal for CI). Failure diagnostics belong on
        # stderr so `make trajectory-check 2>diag.log` captures them.
        print(file=sys.stderr)
        print("Failures:", file=sys.stderr)
        for (skill, scenario, adapter), (passed, total, failures) in sorted(by_key.items()):
            if passed == total:
                continue
            print(f"  {skill}/{scenario} on {adapter}:", file=sys.stderr)
            for f in failures[:5]:
                print(f"    - {f}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the cross-adapter trajectory harness."
    )
    parser.add_argument("--skill", help="Restrict to one skill slug.")
    parser.add_argument(
        "--adapter", help="Restrict to one adapter (claude-code, codex, ...)."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Adapter unavailable counts as hard failure (default: degraded).",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="After DSL passes, run the LLM judge against the trajectory "
        "rubric (Phase 2A). Requires ANTHROPIC_API_KEY.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Per-cell timeout in seconds for the Claude Code spawn.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count cells but do not invoke the provider or judge. Useful "
        "for budgeting before wiring nightly cron (Phase 2C-alpha).",
    )
    parser.add_argument(
        "--max-spawns",
        type=int,
        default=None,
        help="Cap the number of live trace_provider invocations. Cells "
        "past the cap are recorded as budget_exhausted.",
    )
    parser.add_argument(
        "--max-judge-calls",
        type=int,
        default=None,
        help="Cap the number of LLM-judge invocations. Independent of "
        "--max-spawns so a small judge budget can run a full DSL pass.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry provider exceptions (TimeoutError, RuntimeError) this "
        "many times before recording infra_fail. Default 0.",
    )
    args = parser.parse_args()

    # Phase 2B: live Claude Code provider is the default. The harness's
    # per-cell try/except converts any RuntimeError / TimeoutError raised
    # here into an `infra_fail` cell, so a missing `claude` binary or a
    # hung agent does not crash the run.
    from adapters.claude_code_provider import ClaudeCodeProvider

    provider = ClaudeCodeProvider(timeout=args.timeout)

    judge_client = None
    if args.judge:
        from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

        try:
            judge_client = HttpAnthropicJudgeClient()
        except ValueError as exc:
            print(f"  error  cannot enable judge: {exc}", file=sys.stderr)
            return 1

    cfg = HarnessConfig(
        repo_root=REPO_ROOT_DEFAULT,
        trace_provider=provider,
        judge_client=judge_client,
        skill_filter=args.skill,
        adapter_filter=args.adapter,
        strict=args.strict,
        max_provider_calls=args.max_spawns,
        max_judge_calls=args.max_judge_calls,
        dry_run=args.dry_run,
        max_retries=args.max_retries,
    )
    try:
        matrix = run_harness(cfg)
    except ValueError as exc:
        # Controlled exit instead of traceback (scripts/AGENTS.md exit-code
        # contract): filter validation errors print to stderr with exit 1.
        print(f"  error  {exc}", file=sys.stderr)
        return 1
    print_summary(matrix)
    return 0 if matrix.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
