"""evaluate_judge end-to-end with fixture client (Phase 2A Task 2).

Tests the full judge contract: build_trace_summary -> build_judge_messages
-> client.score_trajectory -> parse_judge_response -> JudgeResult.

The fixture client lets us test the orchestration logic without ever
hitting the Anthropic API. The real Anthropic client (Task 3) is tested
separately with mocked urlopen.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trajectory():
    """Build a stub Trajectory with a non-empty rubric."""
    from adapters._protocol import Trajectory

    return Trajectory(
        path=Path("/tmp/x.yaml"),
        skill="demo",
        scenario="happy-path",
        frontmatter={},
        body="",
        input_phrasings=["x"],
        assertions=[],
        llm_judge={
            "threshold": 0.7,
            "rubric": "Did the agent write a markdown file?",
            "model": "claude-sonnet-4-6",
        },
        adapter_scope=["claude-code"],
        model_pinned="claude-opus-4-7",
    )


def _make_trace():
    from adapters.trace_record import TraceEvent, TraceRecord

    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s1",
        prompt="write a markdown file",
        events=[
            TraceEvent(
                seq=0, kind="tool_call", name="Write",
                arguments={"path": "out.md"}, duration_ms=8, raw_attrs={},
            ),
        ],
        artifacts={"out.md": "sha256:abc"},
        total_input_tokens=10,
        total_output_tokens=20,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


class _FixtureClient:
    """Fixture JudgeClient that returns a canned JudgeResult."""

    def __init__(self, response_text: str, model: str = "claude-sonnet-4-6"):
        self._response = response_text
        self._model = model
        self.calls: list[tuple[str, str, str, float]] = []

    def score_trajectory(
        self, rubric: str, trace_summary: str, model: str,
        temperature: float = 0.0,
    ):
        from trajectory_judge import parse_judge_response

        self.calls.append((rubric, trace_summary, model, temperature))
        return parse_judge_response(self._response, model)


def test_evaluate_judge_pipes_rubric_and_summary_to_client() -> None:
    from trajectory_judge import evaluate_judge

    client = _FixtureClient(
        '{"score": 0.85, "reasoning": "Wrote markdown as required."}'
    )
    traj = _make_trajectory()
    trace = _make_trace()
    result = evaluate_judge(traj, trace, client)

    assert result.score == 0.85
    assert "markdown" in result.reasoning.lower()
    assert len(client.calls) == 1
    rubric, summary, model, temperature = client.calls[0]
    assert rubric == "Did the agent write a markdown file?"
    assert "Write" in summary
    assert "out.md" in summary
    assert model == "claude-sonnet-4-6"
    assert temperature == 0.0


def test_evaluate_judge_clamps_out_of_range_score() -> None:
    from trajectory_judge import evaluate_judge

    client = _FixtureClient('{"score": 1.5, "reasoning": "too high"}')
    result = evaluate_judge(_make_trajectory(), _make_trace(), client)
    assert result.score == 1.0


def test_evaluate_judge_handles_unparseable_response() -> None:
    """A judge that returns prose-only should not crash the harness."""
    from trajectory_judge import evaluate_judge

    client = _FixtureClient("Sorry, I cannot judge that.")
    result = evaluate_judge(_make_trajectory(), _make_trace(), client)
    assert result.score == 0.0
    assert "json" in result.reasoning.lower()


def test_evaluate_judge_uses_temperature_zero_by_default() -> None:
    """ADR-0046 hybrid contract: judge runs at temperature=0 to reduce
    calibration noise. Override is allowed for explicit drift testing."""
    from trajectory_judge import evaluate_judge

    client = _FixtureClient('{"score": 0.5, "reasoning": "x"}')
    evaluate_judge(_make_trajectory(), _make_trace(), client)
    _, _, _, t = client.calls[0]
    assert t == 0.0


def test_evaluate_judge_summary_includes_tool_calls_in_order() -> None:
    """The trace summary the judge sees must preserve the tool-call order;
    the rubric often grades how the agent sequenced its actions."""
    from adapters.trace_record import TraceEvent, TraceRecord
    from trajectory_judge import evaluate_judge

    client = _FixtureClient('{"score": 0.5, "reasoning": "x"}')
    trace = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s1",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="skill_load", name="demo",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Read",
                       arguments={"path": "a.py"},
                       duration_ms=5, raw_attrs={}),
            TraceEvent(seq=2, kind="tool_call", name="Write",
                       arguments={"path": "b.md"},
                       duration_ms=8, raw_attrs={}),
        ],
        artifacts={"b.md": "sha256:x"},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    evaluate_judge(_make_trajectory(), trace, client)
    summary = client.calls[0][1]
    # Order must be Read before Write in the summary text.
    assert summary.index("Read") < summary.index("Write")
