"""Judge calibration check (Phase 2C-β).

The hybrid match contract (ADR-0046) says judges should be as
deterministic as possible. Even at temperature=0, real judges produce
small variance because the underlying LLM has prompt-dependent
sampling. The calibration tool runs each rubric N times against a
fixed trace and reports per-rubric variance so authors can detect
flaky rubrics before they pollute the matrix.

A rubric whose score variance exceeds 0.1 between consecutive
temperature=0 runs is too subjective for the hybrid contract; either
tighten it or drop the LLM-judge half for that trajectory.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trajectory(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "base" / "skills" / "engineering" / "demo"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: stub\nversion: 0.1.0\n"
        "owner: t\nlast_reviewed: 2026-05-28\n---\n\n# demo\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / "demo"
    traj_dir.mkdir(parents=True, exist_ok=True)
    path = traj_dir / "happy-path.yaml"
    path.write_text(
        """---
name: demo/happy-path
description: t
skill: demo
scenario: happy-path
version: 0.1.0
owner: t
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:
  phrasings:
    - "x"

assertions:
  - first_skill_loaded: demo

llm_judge:
  threshold: 0.7
  rubric: "Did the agent do the right thing?"
  model: claude-sonnet-4-6
""",
        encoding="utf-8",
    )
    return path


def _fixture_trace():
    from adapters.trace_record import TraceEvent, TraceRecord

    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="cal",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="skill_load", name="demo",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Write",
                       arguments={"path": "out.md"}, duration_ms=5,
                       raw_attrs={}),
        ],
        artifacts={"out.md": "sha256:a"},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


class _StableClient:
    """Judge that always returns the same score (variance = 0)."""

    def __init__(self, score: float):
        self._score = score
        self.calls = 0

    def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
        from trajectory_judge import JudgeResult
        self.calls += 1
        return JudgeResult(
            score=self._score, reasoning="stable",
            raw_response="", model=model,
        )


class _NoisyClient:
    """Judge whose score varies across calls (returns a cycle of values)."""

    def __init__(self, scores: list[float]):
        self._scores = list(scores)
        self._idx = 0
        self.calls = 0

    def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
        from trajectory_judge import JudgeResult
        self.calls += 1
        score = self._scores[self._idx % len(self._scores)]
        self._idx += 1
        return JudgeResult(
            score=score, reasoning=f"call {self.calls}",
            raw_response="", model=model,
        )


def test_calibrate_runs_rubric_n_times_against_fixed_trace(tmp_path: Path) -> None:
    from trajectory_calibrate import calibrate_trajectory

    _make_trajectory(tmp_path)
    client = _StableClient(score=0.85)
    from adapters._loader import PlaybookContent

    content = PlaybookContent.load(tmp_path)
    traj = content.trajectories[0]
    report = calibrate_trajectory(
        trajectory=traj,
        trace=_fixture_trace(),
        client=client,
        runs=5,
    )
    assert client.calls == 5
    assert report.skill == "demo"
    assert report.scenario == "happy-path"
    assert report.runs == 5
    assert len(report.scores) == 5
    assert all(s == 0.85 for s in report.scores)


def test_calibrate_reports_zero_variance_for_stable_rubric(tmp_path: Path) -> None:
    from trajectory_calibrate import calibrate_trajectory

    _make_trajectory(tmp_path)
    client = _StableClient(score=0.85)
    from adapters._loader import PlaybookContent

    traj = PlaybookContent.load(tmp_path).trajectories[0]
    report = calibrate_trajectory(
        trajectory=traj, trace=_fixture_trace(),
        client=client, runs=3,
    )
    assert report.variance == 0.0
    assert report.is_noisy is False


def test_calibrate_flags_rubric_above_variance_threshold(tmp_path: Path) -> None:
    """ADR-0046 reject-if: judge noise above 0.1 between consecutive
    temp=0 runs flips the trajectory to is_noisy=True."""
    from trajectory_calibrate import calibrate_trajectory

    _make_trajectory(tmp_path)
    # Scores span 0.4 from min to max -> well above the 0.1 threshold.
    client = _NoisyClient(scores=[0.5, 0.7, 0.9, 0.5, 0.7])
    from adapters._loader import PlaybookContent

    traj = PlaybookContent.load(tmp_path).trajectories[0]
    report = calibrate_trajectory(
        trajectory=traj, trace=_fixture_trace(),
        client=client, runs=5, noise_threshold=0.1,
    )
    assert report.is_noisy is True
    assert report.variance > 0.1


def test_calibrate_returns_summary_with_min_max_median(tmp_path: Path) -> None:
    """The calibration report includes min/max/median so authors see
    which run produced the outlier."""
    from trajectory_calibrate import calibrate_trajectory

    _make_trajectory(tmp_path)
    client = _NoisyClient(scores=[0.3, 0.7, 0.6, 0.8, 0.5])
    from adapters._loader import PlaybookContent

    traj = PlaybookContent.load(tmp_path).trajectories[0]
    report = calibrate_trajectory(
        trajectory=traj, trace=_fixture_trace(),
        client=client, runs=5,
    )
    assert report.min_score == 0.3
    assert report.max_score == 0.8
    # Median of [0.3, 0.5, 0.6, 0.7, 0.8] = 0.6
    assert report.median_score == 0.6


def test_calibrate_command_can_be_invoked_from_cli(tmp_path: Path, capsys) -> None:
    """The --json flag emits a machine-readable report."""
    import io
    from contextlib import redirect_stdout

    _make_trajectory(tmp_path)
    import trajectory_calibrate

    class _StubClientFactory:
        def __call__(self):
            return _StableClient(score=0.9)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = trajectory_calibrate.main(
            repo_root=tmp_path,
            skill="demo",
            scenario="happy-path",
            runs=3,
            json_output=True,
            client_factory=_StubClientFactory(),
            trace_provider=lambda traj: _fixture_trace(),
        )
    assert rc == 0
    output = buf.getvalue()
    assert "variance" in output
    assert "is_noisy" in output
