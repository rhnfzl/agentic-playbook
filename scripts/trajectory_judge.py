#!/usr/bin/env python3
"""LLM-judge half of the trajectory match contract (Phase 2A, ADR-0046).

The DSL matcher (scripts/trajectory_matcher.py) is the deterministic
gate. The judge runs second, only when DSL passes, and scores the trace
against the trajectory's `llm_judge.rubric`. Threshold gating is
applied by the caller (harness or verify CLI).

This module is pure logic + protocol. The real Anthropic client lives
in `scripts/adapters/anthropic_judge_client.py` (Phase 2A Task 3); tests
inject a fixture client.
"""

from __future__ import annotations

import json
from typing import NamedTuple, Protocol


class JudgeResult(NamedTuple):
    """Per-(trajectory, trace) judge verdict.

    score          -- in [0, 1]; the trajectory's threshold gates pass/fail.
    reasoning      -- short text from the judge explaining the score; surfaces
                      in the harness report when below threshold.
    raw_response   -- full LLM response, kept for debugging score-parse
                      failures or rubric drift investigations.
    model          -- which model produced the score (so the report can
                      note drift if `model` differs from the trajectory's
                      `llm_judge.model`).
    """

    score: float
    reasoning: str
    raw_response: str
    model: str


class JudgeClient(Protocol):
    """Inject any object that satisfies this signature; the harness does
    not care whether it talks to the Anthropic API, a fixture file, or a
    local model."""

    def score_trajectory(
        self,
        rubric: str,
        trace_summary: str,
        model: str,
        temperature: float = 0.0,
    ) -> JudgeResult: ...


def build_judge_messages(rubric: str, trace_summary: str) -> list[dict]:
    """Pure: assemble the messages list the client will send. Kept as a
    helper so tests can lock the exact prompt shape."""
    return [
        {
            "role": "user",
            "content": (
                f"## Rubric\n\n{rubric}\n\n## Trace summary\n\n"
                f"{trace_summary}\n\nScore the trace against the rubric."
            ),
        },
    ]


def parse_judge_response(raw: str, model: str) -> JudgeResult:
    """Pure: extract a JudgeResult from the judge's raw text.

    Tries strict JSON first. Falls back to scanning for the first
    well-formed JSON object in the response (handles judges that wrap
    JSON in prose despite the system prompt). Returns score=0.0 with
    a clear reasoning string when parsing fails entirely so the caller
    can surface the failure in the harness report rather than crashing.
    """
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return JudgeResult(
                score=0.0,
                reasoning=(
                    "judge response did not contain parseable JSON; "
                    "raw response kept for debugging"
                ),
                raw_response=raw,
                model=model,
            )
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return JudgeResult(
                score=0.0,
                reasoning=(
                    "judge response contained brace-bounded text but "
                    "JSON parse failed; raw response kept for debugging"
                ),
                raw_response=raw,
                model=model,
            )

    score_raw = data.get("score")
    reasoning = str(data.get("reasoning", "")).strip() or "(no reasoning)"
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return JudgeResult(
            score=0.0,
            reasoning=f"judge returned non-numeric score: {score_raw!r}",
            raw_response=raw,
            model=model,
        )
    score = max(0.0, min(1.0, score))
    return JudgeResult(
        score=score,
        reasoning=reasoning,
        raw_response=raw,
        model=model,
    )


def build_trace_summary(trace) -> str:  # type: ignore[no-untyped-def]
    """Produce a compact human-readable summary of a TraceRecord.

    The judge does not need the full TraceRecord (session_id, tokens,
    raw_attrs all add noise). It needs: which skill loaded, what tools
    were called and in what order, what artifacts the run produced.

    Output order matches event order; tool_call arguments appear with
    their path (or first argument) so the judge can attribute file
    writes correctly.
    """
    lines: list[str] = []
    lines.append(f"Prompt: {trace.prompt}")
    lines.append(f"Adapter: {trace.adapter}")
    lines.append(f"Model: {trace.model}")
    lines.append("")
    lines.append("Events (in order):")
    for event in trace.events:
        suffix = ""
        if event.arguments:
            for key in ("path", "file_path", "notebook_path"):
                if key in event.arguments:
                    suffix = f" {key}={event.arguments[key]!r}"
                    break
        lines.append(f"  {event.seq:>3}. {event.kind} {event.name}{suffix}")
    if trace.artifacts:
        lines.append("")
        lines.append(f"Artifacts produced: {sorted(trace.artifacts)}")
    return "\n".join(lines)


def evaluate_judge(trajectory, trace, client: JudgeClient) -> JudgeResult:  # type: ignore[no-untyped-def]
    """Run the LLM judge against a (trajectory, trace) pair.

    The trajectory's `llm_judge.rubric` and `llm_judge.model` drive the
    call; the trajectory's threshold is applied by the CALLER (not
    here) so this function stays pure to "produce a score." The
    harness/verify CLI uses the score with the threshold to gate.

    Temperature is fixed at 0.0 to match the ADR-0046 hybrid contract
    (judges should be as deterministic as possible). Drift testing
    that wants a non-zero temperature should call the client directly.
    """
    rubric = trajectory.llm_judge.get("rubric", "").strip()
    model = trajectory.llm_judge.get("model", "claude-sonnet-4-6").strip()
    if not rubric:
        return JudgeResult(
            score=0.0,
            reasoning="trajectory has empty llm_judge.rubric; nothing to score",
            raw_response="",
            model=model,
        )
    summary = build_trace_summary(trace)
    return client.score_trajectory(
        rubric=rubric,
        trace_summary=summary,
        model=model,
        temperature=0.0,
    )
