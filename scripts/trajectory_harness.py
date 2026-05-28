#!/usr/bin/env python3
"""Trajectory harness CLI (Phase 2C, ADR-0044 + ADR-0046).

Loads trajectories from the playbook's content, runs each phrasing
against the trace_provider for every adapter in the trajectory's
adapter_scope, and produces a pass/fail matrix.

Shipped behavior (was "Phase 1 contract" before the Phase 2 fold):

  * Default `trace_provider` is the live `ClaudeCodeProvider` (Phase
    2B). Tests inject a synthetic provider via `HarnessConfig`.
  * The DSL matcher (`scripts/trajectory_matcher.py`) evaluates the
    deterministic assertions per ADR-0046 step 1.
  * When `judge_client` is wired (Phase 2A; `--judge` flag), the LLM
    judge evaluates the rubric after DSL passes. The hybrid contract
    requires BOTH to clear for the cell to pass.
  * Cost-ceiling and retry hooks (Phase 2C-alpha) bound the spend:
    `max_provider_calls` counts every spawn (initial + retries) so a
    `--max-spawns=N` ceiling is honored even when `--max-retries>0`;
    `max_judge_calls` caps LLM-judge invocations independently; a
    judge required by the trajectory but unavailable due to budget
    exhaustion fails the cell (review-fold #3, ADR-0046).
  * `--strict` refuses to start a run if any trajectory has an
    `llm_judge` block but the harness was launched without
    `--judge`/`judge_client`. Surfaces a class of silent
    DSL-only-pass before any spawn happens.

CLI:

  python3 scripts/trajectory_harness.py [--skill <name>] [--adapter <name>]

  make trajectory-check                # all trajectories x all adapters
  make trajectory-check SKILL=to-prd   # narrow to one skill
  make trajectory-check JUDGE=1        # enable the hybrid match
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

    `trace_provider` is the seam between fixture-driven test runs and
    live Claude Code sessions. Contract:

      provider(trajectory, phrasing, adapter) -> TraceRecord

    The provider is responsible for spawning the adapter, capturing the
    trace, and returning a TraceRecord. Exceptions raised by the
    provider propagate so the harness can mark the cell as infra_fail.

    `judge_client` is the Phase 2A LLM-judge seam. When set, the
    harness runs the rubric after the DSL matcher passes; both must
    clear for the cell to pass. None means DSL-only.

    Cost / retry budget (Phase 2C-alpha; review-fold #3):

    * `max_provider_calls` caps the TOTAL number of trace_provider
      invocations, including retries (review-fold P2 finding: previous
      behavior counted only the initial call, so `--max-spawns=3
      --max-retries=2` could spawn up to 9 subprocesses despite the
      advertised ceiling). None means unlimited.
    * `max_judge_calls` caps the LLM-judge invocations independently
      from the provider budget. None means unlimited. When the judge
      budget is exhausted and a trajectory has llm_judge configured,
      the cell fails (review-fold #3, ADR-0046).
    * `dry_run=True` counts cells without invoking provider or judge.
    * `max_retries` retries provider exceptions (TimeoutError,
      RuntimeError). Default 0. Backoff: `retry_backoff_s * (2 ** k)`.

    `skill_filter` / `adapter_filter` narrow the run to one slug each.
    `strict` refuses to start a run if any candidate trajectory has an
    `llm_judge` block but `judge_client` is None (review-fold: removes
    the silent DSL-only-pass case where the judge half was intended
    but never wired).
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


@dataclass
class _HarnessCounters:
    """Mutable spawn / judge counters threaded through the cell loop.

    Lives outside HarnessConfig because the config is frozen (its
    contents define a run; counters are run-state). The counters are
    incremented via `_consume_provider_budget` and `_consume_judge_budget`
    so all increments happen in one place and the retry loop cannot
    skip a count by accident.
    """

    provider_calls: int = 0
    judge_calls: int = 0


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
    consume_budget: Callable[[], bool] | None = None,
) -> "TraceRecord | Exception":
    """Wrap the provider call in a retry loop. Returns either the
    TraceRecord on success or the FINAL exception after exhausting
    retries.

    Retries on TimeoutError and RuntimeError only, since those are the
    classes the ClaudeCodeProvider raises for transient failures
    (timeout, non-zero exit from a crashed `claude`). Other exceptions
    (ValueError on bad adapter, KeyboardInterrupt) propagate
    immediately because retrying them won't help.

    Backoff is exponential: `backoff_s * (2 ** attempt)` where attempt
    is 0-indexed. Tests set backoff_s=0 so they don't slow the suite.

    `consume_budget` is the per-attempt budget gate. It is called
    BEFORE each subprocess spawn (initial attempt + every retry); if it
    returns False the loop stops with either the last seen exception
    or a synthetic budget-exhausted RuntimeError. Folds the cost
    ceiling into the retry path so a `--max-spawns=3 --max-retries=2`
    user spawns at most 3 subprocesses total (review-fold P2: previous
    behavior counted only the initial attempt).
    """
    import time as _time

    attempt = 0
    last_exc: Exception | None = None
    while attempt <= max_retries:
        if consume_budget is not None and not consume_budget():
            # Budget ran out. Always surface this as a budget_exhausted
            # exception so `_evaluate_cell` routes the cell to the right
            # failure label. Without this wrap, a mid-retry exhaustion
            # would return the last transient exception verbatim and the
            # cell would land as `infra_fail` instead of
            # `budget_exhausted` (adversarial review-fold finding).
            if last_exc is not None:
                return RuntimeError(
                    f"budget_exhausted: max_provider_calls reached "
                    f"mid-retry after {attempt} attempt(s); last "
                    f"transient error was {type(last_exc).__name__}: "
                    f"{last_exc}"
                )
            return RuntimeError(
                "budget_exhausted: max_provider_calls reached before "
                "the first attempt could start"
            )
        try:
            return provider(trajectory, phrasing, adapter)
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if attempt < max_retries and backoff_s > 0:
                _time.sleep(backoff_s * (2**attempt))
            attempt += 1
        except Exception as exc:
            # Non-retriable: ValueError (bad adapter), etc.
            return exc
    assert last_exc is not None
    return last_exc


def _make_provider_budget_consumer(
    cfg: HarnessConfig,
    counters: _HarnessCounters,
) -> Callable[[], bool]:
    """Return a per-attempt budget hook for `_call_provider_with_retry`.

    Each call checks whether `provider_calls < max_provider_calls`. If
    headroom exists the counter increments and the function returns
    True (caller may spawn). If no headroom remains the counter does
    NOT increment and the function returns False (caller aborts). A
    `None` cap acts as unlimited.
    """

    def _consume() -> bool:
        if (
            cfg.max_provider_calls is not None
            and counters.provider_calls >= cfg.max_provider_calls
        ):
            return False
        counters.provider_calls += 1
        return True

    return _consume


def _consume_judge_budget(
    cfg: HarnessConfig,
    counters: _HarnessCounters,
) -> bool:
    """Check + consume one slot in the judge budget. Mirrors the
    provider variant but as a one-shot call (no retry on judge)."""
    if cfg.max_judge_calls is not None and counters.judge_calls >= cfg.max_judge_calls:
        return False
    counters.judge_calls += 1
    return True


def _evaluate_cell(
    cfg: HarnessConfig,
    trajectory: Trajectory,
    phrasing: str,
    adapter: str,
    counters: _HarnessCounters,
) -> MatrixCell:
    """Run one (trajectory, phrasing, adapter) cell and return its result.

    Extracted from `run_harness` so the cell-level decision tree
    (dry-run, budget, retry, DSL, judge, judge-budget) sits in one
    testable block (review-fold thermo-nuclear #2: prior version was a
    170-line nested loop where each concern added another `if` at the
    same indentation).
    """

    def _cell(passed: bool, failures: list[str]) -> MatrixCell:
        return MatrixCell(
            skill=trajectory.skill,
            scenario=trajectory.scenario,
            phrasing=phrasing,
            adapter=adapter,
            passed=passed,
            failures=failures,
        )

    if cfg.dry_run:
        return _cell(False, ["dry_run: cell counted, not executed"])

    if (
        cfg.max_provider_calls is not None
        and counters.provider_calls >= cfg.max_provider_calls
    ):
        # Refuse to start a cell whose first attempt cannot afford a
        # spawn. The retry loop also rechecks per attempt; this guard
        # is the "no first attempt at all" case so its message names
        # the cell-start condition, not the mid-retry condition.
        return _cell(
            False,
            [f"budget_exhausted: max_provider_calls={cfg.max_provider_calls} reached"],
        )

    trace_or_exc = _call_provider_with_retry(
        cfg.trace_provider,
        trajectory,
        phrasing,
        adapter,
        max_retries=cfg.max_retries,
        backoff_s=cfg.retry_backoff_s,
        consume_budget=_make_provider_budget_consumer(cfg, counters),
    )
    if isinstance(trace_or_exc, Exception):
        exc = trace_or_exc
        # Distinguish mid-retry budget exhaustion from a true provider
        # crash so the matrix output routes to the right CI action.
        # `_call_provider_with_retry` synthesizes a RuntimeError whose
        # message starts with `budget_exhausted:` when the retry loop's
        # consume_budget callable runs out of slots; that case is a
        # cost-ceiling event, not infra. Adversarial review-fold finding:
        # both used to land as `infra_fail` so an operator could not see
        # the difference between "we hit our spawn cap" and "the agent
        # crashed".
        msg = str(exc)
        if msg.startswith("budget_exhausted:"):
            return _cell(
                False,
                [
                    f"budget_exhausted: max_provider_calls="
                    f"{cfg.max_provider_calls} reached during retry "
                    f"({type(exc).__name__})"
                ],
            )
        return _cell(
            False, [f"infra_fail: trace_provider raised {type(exc).__name__}: {exc}"]
        )

    trace = trace_or_exc
    result = evaluate_assertions(trajectory.assertions, trace)
    failures = list(result.failures)
    passed = result.passed

    # Hybrid match (ADR-0046): when DSL passes AND a judge is wired AND
    # the trajectory has an llm_judge block, the cell passes only if
    # the judge score clears the threshold. Judge-budget exhaustion is
    # a CELL FAILURE (review-fold P2): the contract is "DSL pass AND
    # judge pass", so an unavailable judge cannot satisfy it.
    #
    # The `trajectory.llm_judge` truthiness check is essential: a
    # trajectory that ships only DSL assertions (no `llm_judge:` block)
    # must skip the judge even when a judge_client is wired. Otherwise
    # we would call `evaluate_judge` with an empty rubric, the LLM
    # would emit garbage, and a stable DSL-only trajectory would
    # spuriously fail because the empty-rubric score landed below the
    # default threshold (Codex review-fold finding).
    if not (passed and cfg.judge_client is not None and trajectory.llm_judge):
        return _cell(passed, failures)

    if not _consume_judge_budget(cfg, counters):
        return _cell(
            False,
            failures
            + [
                f"judge_budget_exhausted: max_judge_calls="
                f"{cfg.max_judge_calls} reached. The hybrid match contract "
                f"(ADR-0046) requires both DSL and judge to pass; without "
                f"a judge score this cell cannot pass."
            ],
        )

    judge_result = evaluate_judge(trajectory, trace, cfg.judge_client)
    threshold = get_threshold(trajectory)
    if judge_result.score < threshold:
        # Distinguish infra failures from quality failures so operators
        # reading the matrix can route a 429 to "retry overnight" and a
        # quality miss to "regression to investigate."
        prefix = "judge_infra_fail" if judge_result.is_infra_error else "llm_judge"
        failures.append(
            f"{prefix}: score {judge_result.score:.2f} "
            f"below threshold {threshold} "
            f"(reasoning: {judge_result.reasoning})"
        )
        return _cell(False, failures)

    return _cell(True, failures)


# Adapter registry lives in adapters/trace_record.py; reuse the frozenset
# rather than maintain a parallel copy here (third-review finding:
# triplicate registry meant Phase 3 shims would silently drift).


def run_harness(cfg: HarnessConfig) -> Matrix:
    """Execute the matrix and return the aggregated result.

    Raises ValueError if filters narrow the run to zero cells (a typo
    like ADAPTER=claud-code would otherwise exit green with zero cells,
    which is misleading CI output) or if `--strict` is on and a
    trajectory has `llm_judge` configured without a judge_client
    wired (silent DSL-only-pass case the strict mode rejects).
    """
    content = PlaybookContent.load(cfg.repo_root)
    matrix = Matrix()

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
            t for t in candidate_trajectories if cfg.adapter_filter in t.adapter_scope
        ]
        if not scopes_with_adapter:
            adapter_options = sorted(
                {a for t in candidate_trajectories for a in t.adapter_scope}
            )
            raise ValueError(
                f"adapter filter '{cfg.adapter_filter}' is valid but no "
                f"trajectory in scope declares it in adapter_scope; "
                f"trajectories use these adapters: {adapter_options}"
            )

    # --strict: refuse to start when judge is required but unwired.
    # Previously --strict was a no-op warning (review-fold P2 #7). Now
    # it catches the silent "trajectory configured an LLM judge but the
    # operator forgot --judge" failure mode before any spawn happens.
    if cfg.strict and cfg.judge_client is None:
        traj_with_judge = [t for t in candidate_trajectories if t.llm_judge]
        if traj_with_judge:
            names = sorted({f"{t.skill}/{t.scenario}" for t in traj_with_judge})
            raise ValueError(
                "strict mode: the following trajectories configure an "
                "llm_judge block but no judge_client was provided to "
                f"the harness: {names}. Either pass --judge (with "
                "ANTHROPIC_API_KEY set) or remove --strict if a "
                "DSL-only run is acceptable."
            )

    counters = _HarnessCounters()
    for traj in candidate_trajectories:
        adapters = traj.adapter_scope
        if cfg.adapter_filter:
            adapters = [a for a in adapters if a == cfg.adapter_filter]
        for adapter in adapters:
            for phrasing in traj.input_phrasings:
                matrix.cells.append(
                    _evaluate_cell(cfg, traj, phrasing, adapter, counters)
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
    for (skill, scenario, adapter), (passed, total, _failures) in sorted(
        by_key.items()
    ):
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
        for (skill, scenario, adapter), (passed, total, failures) in sorted(
            by_key.items()
        ):
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
        help="Refuse to start the run if any candidate trajectory has "
        "an llm_judge block but --judge was not passed (no judge_client "
        "wired). Catches the silent DSL-only-pass mode where the "
        "operator intended the hybrid contract but forgot the flag.",
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
