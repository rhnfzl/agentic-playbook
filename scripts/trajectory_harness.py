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

    for traj in candidate_trajectories:
        adapters = traj.adapter_scope
        if cfg.adapter_filter:
            adapters = [a for a in adapters if a == cfg.adapter_filter]

        for adapter in adapters:
            for phrasing in traj.input_phrasings:
                try:
                    trace = cfg.trace_provider(traj, phrasing, adapter)
                except Exception as exc:
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

                result = evaluate_assertions(traj.assertions, trace)
                failures = list(result.failures)
                passed = result.passed

                # Phase 2A: if DSL passed AND a judge_client is wired,
                # run the LLM judge and gate on the trajectory threshold.
                # DSL failures short-circuit the judge to save cost.
                if passed and cfg.judge_client is not None:
                    judge_result = evaluate_judge(traj, trace, cfg.judge_client)
                    threshold = get_threshold(traj)
                    if judge_result.score < threshold:
                        passed = False
                        # Distinguish infra failures from quality failures
                        # so operators reading the matrix can route a 429
                        # to "retry overnight" and a quality miss to
                        # "regression to investigate."
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
    args = parser.parse_args()

    def _missing_provider(_traj, _phrasing, _adapter):
        """Phase 1 CLI default: the live trace provider is Phase 2 work.
        Calling the CLI without a custom provider explicitly errors so
        no one mistakes the matrix for a real test run."""
        raise RuntimeError(
            "trace_provider not configured; Phase 1 CLI requires tests "
            "to inject a provider. Phase 2 ships the live Claude Code "
            "spawner that wires this automatically."
        )

    cfg = HarnessConfig(
        repo_root=REPO_ROOT_DEFAULT,
        trace_provider=_missing_provider,
        skill_filter=args.skill,
        adapter_filter=args.adapter,
        strict=args.strict,
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
