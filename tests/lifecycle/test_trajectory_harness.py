"""Trajectory harness CLI (Phase 1, ADR-0046).

The harness loads trajectories from PlaybookContent, runs each against
fixture TraceRecords (the live-agent runner is a separate Phase 2 task),
and produces a matrix report.

This test suite drives the harness with synthetic fixture traces so the
CLI logic is exercised without spawning Claude Code. Phase 2 adds a
live-runner; the matrix output and CLI contract are locked here so
Phase 2's only job is to swap fixture loading for real spawning.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trajectory(
    tmp_path: Path,
    *,
    skill: str = "demo",
    scenario: str = "happy-path",
    assertions_block: str | None = None,
    phrasings_block: str | None = None,
) -> Path:
    """Build a trajectory file on disk."""
    skill_dir = tmp_path / "base" / "skills" / "engineering" / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: " + skill + "\ndescription: demo\nversion: 0.1.0\n"
        "owner: test\nlast_reviewed: 2026-05-28\n---\n\n# " + skill + "\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / skill
    traj_dir.mkdir(parents=True, exist_ok=True)
    phrasings = phrasings_block or (
        '    - "phrasing one"\n'
        '    - "phrasing two"\n'
        '    - "phrasing three"\n'
        '    - "phrasing four"\n'
        '    - "phrasing five"\n'
    )
    assertions = assertions_block or (
        f"  - first_skill_loaded: {skill}\n"
        f"  - must_invoke_tool: Write\n"
    )
    body = (
        f"---\n"
        f"name: {skill}/{scenario}\n"
        f"description: test trajectory\n"
        f"skill: {skill}\n"
        f"scenario: {scenario}\n"
        f"version: 0.1.0\n"
        f"owner: test\n"
        f"last_reviewed: 2026-05-28\n"
        f"adapter_scope: [claude-code]\n"
        f"model_pinned: claude-opus-4-7\n"
        f"---\n\n"
        f"input:\n"
        f"  phrasings:\n"
        f"{phrasings}\n"
        f"assertions:\n"
        f"{assertions}\n"
        f"llm_judge:\n"
        f"  threshold: 0.7\n"
        f'  rubric: "test"\n'
        f"  model: claude-sonnet-4-6\n"
    )
    traj_path = traj_dir / f"{scenario}.yaml"
    traj_path.write_text(body, encoding="utf-8")
    return traj_path


def _fixture_trace(
    *,
    skill: str = "demo",
    include_write: bool = True,
    include_bash: bool = False,
):
    """Synthetic TraceRecord that satisfies the default assertions."""
    from datetime import datetime, timezone
    from adapters.trace_record import TraceEvent, TraceRecord

    events = [
        TraceEvent(
            seq=0, kind="skill_load", name=skill,
            arguments=None, duration_ms=None, raw_attrs={},
        ),
    ]
    if include_write:
        events.append(TraceEvent(
            seq=len(events), kind="tool_call", name="Write",
            arguments={"path": "out.md"}, duration_ms=5, raw_attrs={},
        ))
    if include_bash:
        events.append(TraceEvent(
            seq=len(events), kind="tool_call", name="Bash",
            arguments=None, duration_ms=5, raw_attrs={},
        ))

    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="t",
        prompt="phrasing one",
        events=events,
        artifacts={"out.md": "sha256:abc"} if include_write else {},
        total_input_tokens=10,
        total_output_tokens=20,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


def test_harness_passes_trajectory_when_trace_satisfies_assertions(
    tmp_path: Path,
) -> None:
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _traj, _phrasing, _adapter: _fixture_trace(),
    )
    matrix = run_harness(cfg)
    assert matrix.total == 1
    assert matrix.passed == 1
    assert matrix.failed == 0


def test_harness_fails_trajectory_when_assertion_fails(tmp_path: Path) -> None:
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(
        tmp_path,
        assertions_block=(
            "  - first_skill_loaded: demo\n"
            "  - must_not_invoke_tool: Bash\n"
        ),
    )
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _traj, _phrasing, _adapter: _fixture_trace(include_bash=True),
    )
    matrix = run_harness(cfg)
    assert matrix.passed == 0
    assert matrix.failed == 1
    assert any("Bash" in f for cell in matrix.cells for f in cell.failures)


def test_harness_runs_every_phrasing_under_parallel_strategy(
    tmp_path: Path,
) -> None:
    """Default variant_strategy is parallel: harness runs all 5 phrasings."""
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    invocations: list[str] = []

    def provider(_traj, phrasing: str, _adapter: str):
        invocations.append(phrasing)
        return _fixture_trace()

    cfg = HarnessConfig(repo_root=tmp_path, trace_provider=provider)
    run_harness(cfg)
    assert len(invocations) == 5
    assert invocations[0] == "phrasing one"
    assert invocations[-1] == "phrasing five"


def test_harness_reports_per_adapter_per_phrasing(tmp_path: Path) -> None:
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _traj, _phrasing, _adapter: _fixture_trace(),
    )
    matrix = run_harness(cfg)
    assert len(matrix.cells) == 5  # 5 phrasings * 1 adapter
    for cell in matrix.cells:
        assert cell.adapter == "claude-code"
        assert cell.skill == "demo"
        assert cell.scenario == "happy-path"


def test_harness_aggregates_skill_filter(tmp_path: Path) -> None:
    """SKILL= filter narrows the run to one skill."""
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path, skill="alpha", scenario="happy-path")
    _make_trajectory(tmp_path, skill="beta", scenario="happy-path")

    def provider(traj, _phrasing, _adapter):
        return _fixture_trace(skill=traj.skill)

    cfg = HarnessConfig(repo_root=tmp_path, trace_provider=provider, skill_filter="alpha")
    matrix = run_harness(cfg)
    assert {c.skill for c in matrix.cells} == {"alpha"}


def test_harness_stdout_summary(tmp_path: Path, capsys) -> None:
    from trajectory_harness import HarnessConfig, print_summary, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _traj, _phrasing, _adapter: _fixture_trace(),
    )
    matrix = run_harness(cfg)
    print_summary(matrix)
    captured = capsys.readouterr()
    assert "demo" in captured.out
    assert "claude-code" in captured.out
    assert "PASS" in captured.out


def test_harness_rejects_unknown_adapter_filter(tmp_path: Path) -> None:
    """Codex review finding: ADAPTER=claud-code typo previously returned
    zero cells (matrix.failed == 0 => exit 0). Now it raises."""
    import pytest as _pytest
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _t, _p, _a: _fixture_trace(),
        adapter_filter="claud-code",
    )
    with _pytest.raises(ValueError, match="claud-code"):
        run_harness(cfg)


def test_harness_rejects_skill_filter_with_no_matches(tmp_path: Path) -> None:
    """Skill filter typo must error instead of silently passing."""
    import pytest as _pytest
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _t, _p, _a: _fixture_trace(),
        skill_filter="no-such-skill",
    )
    with _pytest.raises(ValueError, match="no-such-skill"):
        run_harness(cfg)


def test_harness_failure_details_route_to_stderr(tmp_path: Path, capsys) -> None:
    """Codex review-round-4: when matrix.failed > 0, the Failures: detail
    block must print to stderr (not stdout) so the stdout/stderr contract
    holds. The matrix table itself stays on stdout."""
    from trajectory_harness import HarnessConfig, print_summary, run_harness

    _make_trajectory(
        tmp_path,
        assertions_block=(
            "  - first_skill_loaded: demo\n"
            "  - must_not_invoke_tool: Bash\n"
        ),
    )
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _t, _p, _a: _fixture_trace(include_bash=True),
    )
    matrix = run_harness(cfg)
    print_summary(matrix)
    captured = capsys.readouterr()
    # Matrix header + table on stdout.
    assert "Trajectory matrix" in captured.out
    assert "FAIL" in captured.out
    # Failure detail block on stderr.
    assert "Failures:" in captured.err
    assert "Bash" in captured.err


def test_harness_strict_mode_warns_in_phase_1(tmp_path: Path) -> None:
    """Codex review finding: --strict is currently a no-op; surface a
    warning so CI that sets STRICT=1 expecting enforcement gets a clear
    advisory rather than silent green pass."""
    import warnings as _warnings
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda _t, _p, _a: _fixture_trace(),
        strict=True,
    )
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        run_harness(cfg)
    assert any("strict" in str(w.message).lower() for w in caught)
