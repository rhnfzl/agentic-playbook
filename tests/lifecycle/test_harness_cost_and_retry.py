"""Cost ceiling + dry-run + retry policy (Phase 2C-α).

Defensive infrastructure that closes the deferred items from the
Phase 2A and Phase 2B review rounds:

  * `max_provider_calls` caps the number of live Claude Code spawns
    per harness run. The default (None) keeps Phase 2B behavior.
  * `max_judge_calls` caps the number of LLM-judge invocations.
  * `dry_run` exits after counting cells; useful for budgeting before
    a nightly cron is wired in.
  * `max_retries` retries transient provider failures (TimeoutError,
    RuntimeError from non-zero exit) with exponential backoff.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trajectory(tmp_path: Path, skill: str = "demo"):
    skill_dir = tmp_path / "base" / "skills" / "engineering" / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: " + skill + "\ndescription: stub\nversion: 0.1.0\n"
        "owner: test\nlast_reviewed: 2026-05-28\n---\n\n# " + skill + "\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / skill
    traj_dir.mkdir(parents=True, exist_ok=True)
    (traj_dir / "happy-path.yaml").write_text(
        f"""---
name: {skill}/happy-path
description: t
skill: {skill}
scenario: happy-path
version: 0.1.0
owner: t
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:
  phrasings:
    - "one"
    - "two"
    - "three"
    - "four"
    - "five"

assertions:
  - first_skill_loaded: {skill}
  - must_invoke_tool: Write

llm_judge:
  threshold: 0.7
  rubric: "x"
  model: claude-sonnet-4-6
""",
        encoding="utf-8",
    )


def _fixture_trace(skill: str = "demo"):
    from adapters.trace_record import TraceEvent, TraceRecord

    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="t",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="skill_load", name=skill,
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Write",
                       arguments={"path": "out.md"}, duration_ms=5, raw_attrs={}),
        ],
        artifacts={"out.md": "sha256:a"},
        total_input_tokens=10,
        total_output_tokens=20,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


# --- max_provider_calls ---


def test_max_provider_calls_caps_spawn_count(tmp_path: Path) -> None:
    """When max_provider_calls=3, the harness stops after 3 cells.
    Remaining cells appear as skipped (passed=False, failure='budget')."""
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    calls = {"n": 0}

    def provider(traj, phrasing, adapter):
        calls["n"] += 1
        return _fixture_trace(skill=traj.skill)

    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        max_provider_calls=3,
    )
    matrix = run_harness(cfg)
    # 5 phrasings -> 5 cells expected; budget caps at 3.
    assert calls["n"] == 3
    assert len(matrix.cells) == 5
    skipped = [c for c in matrix.cells if not c.passed]
    assert len(skipped) == 2
    assert any("budget" in f for cell in skipped for f in cell.failures)


def test_max_provider_calls_default_is_unlimited(tmp_path: Path) -> None:
    """Without max_provider_calls, the harness runs every cell."""
    from trajectory_harness import HarnessConfig, run_harness

    _make_trajectory(tmp_path)
    calls = {"n": 0}

    def provider(traj, phrasing, adapter):
        calls["n"] += 1
        return _fixture_trace()

    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
    )
    run_harness(cfg)
    assert calls["n"] == 5


# --- max_judge_calls ---


def test_max_judge_calls_caps_judge_invocations(tmp_path: Path) -> None:
    """LLM judge budget is independent of provider budget. The DSL still
    runs on every cell; the judge stops after the cap."""
    from trajectory_harness import HarnessConfig, run_harness
    from trajectory_judge import JudgeResult

    judge_calls = {"n": 0}

    class _StubClient:
        def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
            judge_calls["n"] += 1
            return JudgeResult(
                score=0.9, reasoning="x", raw_response="",
                model="claude-sonnet-4-6",
            )

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda t, p, a: _fixture_trace(),
        judge_client=_StubClient(),
        max_judge_calls=2,
    )
    run_harness(cfg)
    assert judge_calls["n"] == 2


# --- dry_run ---


def test_dry_run_skips_provider_and_judge(tmp_path: Path) -> None:
    """dry_run=True: count cells but never call provider or judge."""
    from trajectory_harness import HarnessConfig, run_harness
    from trajectory_judge import JudgeResult

    provider_calls = {"n": 0}
    judge_calls = {"n": 0}

    def provider(t, p, a):
        provider_calls["n"] += 1
        return _fixture_trace()

    class _StubClient:
        def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
            judge_calls["n"] += 1
            return JudgeResult(score=0.9, reasoning="", raw_response="", model="x")

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        judge_client=_StubClient(),
        dry_run=True,
    )
    matrix = run_harness(cfg)
    assert provider_calls["n"] == 0
    assert judge_calls["n"] == 0
    # Dry-run still produces a matrix with planned cells.
    assert len(matrix.cells) == 5
    # Every cell is reported as a dry-run skip, not as pass or fail.
    for cell in matrix.cells:
        assert any("dry_run" in f for f in cell.failures)


# --- max_retries ---


def test_max_retries_zero_propagates_first_failure(tmp_path: Path) -> None:
    """Default max_retries=0: provider exception goes straight to infra_fail."""
    from trajectory_harness import HarnessConfig, run_harness

    attempts = {"n": 0}

    def provider(t, p, a):
        attempts["n"] += 1
        raise RuntimeError("boom")

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
    )
    run_harness(cfg)
    # 5 cells x 1 attempt each = 5 calls total.
    assert attempts["n"] == 5


def test_max_retries_retries_until_success(tmp_path: Path) -> None:
    """max_retries=2: the first 2 attempts fail, the 3rd succeeds."""
    from trajectory_harness import HarnessConfig, run_harness

    attempts_per_cell: dict = {}

    def provider(t, p, a):
        attempts_per_cell.setdefault(p, 0)
        attempts_per_cell[p] += 1
        if attempts_per_cell[p] < 3:
            raise TimeoutError("transient")
        return _fixture_trace()

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        max_retries=2,
        retry_backoff_s=0.0,  # no sleep in tests
    )
    matrix = run_harness(cfg)
    assert all(n == 3 for n in attempts_per_cell.values())
    assert matrix.passed == 1


def test_max_retries_records_final_failure_after_exhausting(tmp_path: Path) -> None:
    """If retries are exhausted, the cell is recorded as infra_fail with
    the original error message."""
    from trajectory_harness import HarnessConfig, run_harness

    def provider(t, p, a):
        raise RuntimeError("rate-limited")

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        max_retries=2,
        retry_backoff_s=0.0,
    )
    matrix = run_harness(cfg)
    assert matrix.failed == 1
    joined = "\n".join(f for c in matrix.cells for f in c.failures)
    assert "infra_fail" in joined
    assert "rate-limited" in joined


# --- review-fold P2: retries count against max_provider_calls ---


def test_retries_count_against_max_provider_calls(tmp_path: Path) -> None:
    """Review-fold P2 finding: previous behavior counted only the
    initial provider call against max_provider_calls, so
    `--max-spawns=3 --max-retries=2` could spawn up to 9 subprocesses.
    The fix: every attempt (initial + retries) consumes one budget
    slot. With max_spawns=3 and an always-failing provider, at most 3
    spawns happen total even when max_retries=5."""
    from trajectory_harness import HarnessConfig, run_harness

    attempts = {"n": 0}

    def provider(t, p, a):
        attempts["n"] += 1
        raise RuntimeError("transient")

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        max_provider_calls=3,
        max_retries=5,
        retry_backoff_s=0.0,
    )
    matrix = run_harness(cfg)
    # 3 spawns max across the run, not 5 cells x 6 attempts each.
    assert attempts["n"] == 3
    # Cells beyond the budget are recorded as budget_exhausted.
    joined = "\n".join(f for c in matrix.cells for f in c.failures)
    assert "budget_exhausted" in joined


def test_retries_inside_one_cell_consume_budget(tmp_path: Path) -> None:
    """A single cell that succeeds on attempt 3 (after 2 transient
    failures) consumes 3 budget slots. The next cell then sees
    budget_exhausted."""
    from trajectory_harness import HarnessConfig, run_harness

    attempts_per_cell: dict = {}

    def provider(t, p, a):
        attempts_per_cell.setdefault(p, 0)
        attempts_per_cell[p] += 1
        if attempts_per_cell[p] < 3:
            raise TimeoutError("transient")
        return _fixture_trace()

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=provider,
        max_provider_calls=3,
        max_retries=2,
        retry_backoff_s=0.0,
    )
    matrix = run_harness(cfg)
    # Exactly one cell finishes (after 3 attempts); the remaining 4
    # cells skip with budget_exhausted.
    successful_cells = [c for c in matrix.cells if c.passed]
    assert len(successful_cells) == 1
    skipped = [c for c in matrix.cells if not c.passed]
    assert len(skipped) == 4
    assert all(
        any("budget_exhausted" in f for f in c.failures)
        for c in skipped
    )


# --- review-fold P2: judge budget exhausted must fail the cell ---


def test_judge_budget_exhausted_fails_the_cell(tmp_path: Path) -> None:
    """Review-fold P2 finding: previously a cell with DSL pass but
    judge budget exhausted stayed passed=True, contradicting ADR-0046's
    'DSL pass AND judge pass' hybrid contract. The fix flips passed to
    False so the matrix shows the cell as failed."""
    from trajectory_harness import HarnessConfig, run_harness
    from trajectory_judge import JudgeResult

    class _PassJudge:
        def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
            return JudgeResult(
                score=0.95, reasoning="ok", raw_response="",
                model="claude-sonnet-4-6",
            )

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda t, p, a: _fixture_trace(),
        judge_client=_PassJudge(),
        max_judge_calls=0,  # budget exhausted before first cell.
    )
    matrix = run_harness(cfg)
    # Every cell DSL-passes but judge budget is zero. Each cell must FAIL.
    assert matrix.passed == 0
    assert matrix.failed == 1  # one trajectory (5 phrasings, all failed)
    assert all(not c.passed for c in matrix.cells)
    joined = "\n".join(f for c in matrix.cells for f in c.failures)
    assert "judge_budget_exhausted" in joined


def test_judge_failures_are_not_retried(tmp_path: Path) -> None:
    """Retry applies only to the provider call. The judge has its own
    is_infra_error flag; harness retries don't compound on judge calls."""
    from trajectory_harness import HarnessConfig, run_harness
    from trajectory_judge import JudgeResult

    judge_calls = {"n": 0}

    class _AlwaysFailClient:
        def score_trajectory(self, rubric, trace_summary, model, temperature=0.0):
            judge_calls["n"] += 1
            return JudgeResult(
                score=0.0, reasoning="HTTP 429", raw_response="",
                model="claude-sonnet-4-6", is_infra_error=True,
            )

    _make_trajectory(tmp_path)
    cfg = HarnessConfig(
        repo_root=tmp_path,
        trace_provider=lambda t, p, a: _fixture_trace(),
        judge_client=_AlwaysFailClient(),
        max_retries=3,  # provider retries; should NOT compound on judge
        retry_backoff_s=0.0,
    )
    run_harness(cfg)
    # 5 cells, judge called once per cell (no retry on judge), so 5 calls.
    assert judge_calls["n"] == 5
