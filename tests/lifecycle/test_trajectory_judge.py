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
                seq=0,
                kind="tool_call",
                name="Write",
                arguments={"path": "out.md"},
                duration_ms=8,
                raw_attrs={},
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
        self,
        rubric: str,
        trace_summary: str,
        model: str,
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


def test_parse_response_detects_refusal_phrase_outside_json() -> None:
    """Adversarial review-round-5 finding: a refusal like "I cannot
    score this. {\"score\": 1.0}" must NOT be trusted. The score=0
    return prevents an embedded number from being read as the verdict."""
    from trajectory_judge import parse_judge_response

    raw = 'I cannot score this. {"score": 1.0, "reasoning": "x"}'
    result = parse_judge_response(raw, model="claude-sonnet-4-6")
    assert result.score == 0.0
    assert "refusal" in result.reasoning.lower()


def test_parse_response_accepts_clean_json_after_thinking() -> None:
    """The refusal guard must not false-positive on legitimate
    thinking-then-JSON responses that contain words like 'cannot
    determine' inside the JSON itself."""
    from trajectory_judge import parse_judge_response

    raw = (
        '{"score": 0.8, "reasoning": "The agent did fine; '
        'one minor gap I could not assess."}'
    )
    result = parse_judge_response(raw, model="claude-sonnet-4-6")
    assert result.score == 0.8


def test_get_threshold_returns_declared_value() -> None:
    """The single-source threshold helper: declared float passes through."""
    from adapters._protocol import Trajectory
    from trajectory_judge import get_threshold

    traj = Trajectory(
        path=Path("/tmp/x.yaml"),
        skill="x",
        scenario="y",
        frontmatter={},
        body="",
        input_phrasings=[],
        assertions=[],
        llm_judge={"threshold": 0.85, "rubric": "x", "model": "x"},
        adapter_scope=[],
        model_pinned="x",
    )
    assert get_threshold(traj) == 0.85


def test_parse_response_handles_non_object_json() -> None:
    """Codex review-round-5 #1: a valid-but-non-object JSON response
    (`[]`, `"ok"`, `42`) previously crashed `data.get('score')` with
    AttributeError. Now returns score=0 with a clear reasoning."""
    from trajectory_judge import parse_judge_response

    for raw in ("[]", '"ok"', "42", "null", "true"):
        result = parse_judge_response(raw, model="claude-sonnet-4-6")
        assert result.score == 0.0, f"crashed or wrongly accepted: {raw!r}"
        assert "score" in result.reasoning.lower() or "json" in result.reasoning.lower()


def test_parse_response_extracts_final_block_from_multi_block_response() -> None:
    """Codex review-round-5 #2: a response with multiple JSON blocks
    (draft followed by final verdict) previously took the outer
    first-to-last slice as one block, failing to parse. Now we try
    the LAST balanced block first."""
    from trajectory_judge import parse_judge_response

    raw = '{"draft": "thinking aloud"}\n{"score": 0.85, "reasoning": "good"}'
    result = parse_judge_response(raw, model="claude-sonnet-4-6")
    assert result.score == 0.85
    assert result.reasoning == "good"


def test_get_threshold_falls_back_to_default_when_malformed() -> None:
    """Non-numeric threshold falls back to 0.7 (linter rejects this at
    PR time; the helper is defense-in-depth at runtime)."""
    from adapters._protocol import Trajectory
    from trajectory_judge import get_threshold

    traj = Trajectory(
        path=Path("/tmp/x.yaml"),
        skill="x",
        scenario="y",
        frontmatter={},
        body="",
        input_phrasings=[],
        assertions=[],
        llm_judge={"threshold": "not-a-number"},
        adapter_scope=[],
        model_pinned="x",
    )
    assert get_threshold(traj) == 0.7


def test_trace_summary_includes_non_path_arguments() -> None:
    """Codex review-round-5 #3: Bash command, query strings, and other
    non-path arguments must appear in the summary so the judge can grade
    them. Previously only path/file_path/notebook_path were surfaced."""
    from adapters.trace_record import TraceEvent, TraceRecord
    from trajectory_judge import build_trace_summary

    trace = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s",
        prompt="x",
        events=[
            TraceEvent(
                seq=0,
                kind="tool_call",
                name="Bash",
                arguments={"command": "ls -la /tmp"},
                duration_ms=5,
                raw_attrs={},
            ),
            TraceEvent(
                seq=1,
                kind="tool_call",
                name="Grep",
                arguments={"pattern": "TODO", "path": "src/"},
                duration_ms=10,
                raw_attrs={},
            ),
        ],
        artifacts={},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    summary = build_trace_summary(trace)
    assert "ls -la" in summary
    assert "TODO" in summary
    assert "src/" in summary


def test_trace_summary_truncates_long_argument_values() -> None:
    """Long argument values get a `...` suffix so a single Write doesn't
    blow up the judge's context window."""
    from adapters.trace_record import TraceEvent, TraceRecord
    from trajectory_judge import build_trace_summary

    trace = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s",
        prompt="x",
        events=[
            TraceEvent(
                seq=0,
                kind="tool_call",
                name="Write",
                arguments={"content": "x" * 500, "path": "out.md"},
                duration_ms=5,
                raw_attrs={},
            ),
        ],
        artifacts={},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    summary = build_trace_summary(trace)
    assert "..." in summary
    # The full 500-char content must not appear verbatim.
    assert "x" * 500 not in summary


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
            TraceEvent(
                seq=0,
                kind="skill_load",
                name="demo",
                arguments=None,
                duration_ms=None,
                raw_attrs={},
            ),
            TraceEvent(
                seq=1,
                kind="tool_call",
                name="Read",
                arguments={"path": "a.py"},
                duration_ms=5,
                raw_attrs={},
            ),
            TraceEvent(
                seq=2,
                kind="tool_call",
                name="Write",
                arguments={"path": "b.md"},
                duration_ms=8,
                raw_attrs={},
            ),
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
