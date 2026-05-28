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
from adapters.trace_record import TraceRecord  # noqa: E402
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

    `skill_filter` narrows the run to one skill (or None for all).
    `adapter_filter` narrows to one adapter (or None for all).
    `strict` flips adapter_unavailable into a hard failure.
    """

    repo_root: Path
    trace_provider: TraceProvider
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


def run_harness(cfg: HarnessConfig) -> Matrix:
    """Execute the matrix and return the aggregated result."""
    content = PlaybookContent.load(cfg.repo_root)
    matrix = Matrix()

    for traj in _iter_trajectories(content, cfg.skill_filter):
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
                matrix.cells.append(
                    MatrixCell(
                        skill=traj.skill,
                        scenario=traj.scenario,
                        phrasing=phrasing,
                        adapter=adapter,
                        passed=result.passed,
                        failures=list(result.failures),
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
        print()
        print("Failures:")
        for (skill, scenario, adapter), (passed, total, failures) in sorted(by_key.items()):
            if passed == total:
                continue
            print(f"  {skill}/{scenario} on {adapter}:")
            for f in failures[:5]:
                print(f"    - {f}")


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
    matrix = run_harness(cfg)
    print_summary(matrix)
    return 0 if matrix.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
