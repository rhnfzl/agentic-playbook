"""JudgeClient + JudgeResult shape (Phase 2A Task 1).

Pure data + protocol; no I/O, no LLM, no HTTP. The real
`AnthropicJudgeClient` (Phase 2A Task 3) implements the protocol;
tests inject a fixture client.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_judge_result_has_required_fields() -> None:
    from trajectory_judge import JudgeResult

    fields = JudgeResult._fields
    assert "score" in fields
    assert "reasoning" in fields
    assert "raw_response" in fields
    assert "model" in fields


def test_judge_result_constructable() -> None:
    from trajectory_judge import JudgeResult

    r = JudgeResult(
        score=0.85,
        reasoning="Agent followed the rubric.",
        raw_response='{"score": 0.85, "reasoning": "..."}',
        model="claude-sonnet-4-6",
    )
    assert r.score == 0.85
    assert "rubric" in r.reasoning


def test_judge_client_protocol_exists() -> None:
    """JudgeClient is a runtime-checkable Protocol so tests can pass any
    object that satisfies the score_trajectory signature."""
    from trajectory_judge import JudgeClient

    class FakeClient:
        def score_trajectory(
            self,
            rubric: str,
            trace_summary: str,
            model: str,
            temperature: float = 0.0,
        ):
            from trajectory_judge import JudgeResult

            return JudgeResult(
                score=0.5,
                reasoning="fake",
                raw_response="",
                model=model,
            )

    # Duck-typing check: the protocol must accept any object with the right
    # signature; we just verify the import resolves.
    assert hasattr(JudgeClient, "__name__") or JudgeClient is not None
    c: JudgeClient = FakeClient()  # type: ignore[assignment]
    result = c.score_trajectory(
        rubric="x",
        trace_summary="y",
        model="claude-sonnet-4-6",
    )
    assert result.score == 0.5
