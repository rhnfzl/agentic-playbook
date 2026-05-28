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

    score              -- in [0, 1]; the trajectory's threshold gates pass/fail.
    reasoning          -- short text from the judge explaining the score;
                          surfaces in the harness report when below threshold.
    raw_response       -- full LLM response, kept for debugging score-parse
                          failures or rubric drift investigations.
    model              -- which model produced the score (so the report can
                          note drift if `model` differs from the trajectory's
                          `llm_judge.model`).
    is_infra_error     -- True when score=0.0 was set by an infrastructure
                          failure (HTTP 429, network timeout, parse error
                          on the judge response), NOT by the judge scoring
                          the trace low. The harness uses this to label
                          failures as `judge_infra_fail` instead of
                          `llm_judge` so operators distinguish a transient
                          ops blip from a genuine agent-quality regression.
                          Mirrors the trace_provider's `infra_fail:` prefix
                          discipline (adversarial review-round-5 finding).
    """

    score: float
    reasoning: str
    raw_response: str
    model: str
    is_infra_error: bool = False


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


_REFUSAL_PHRASES = (
    "i cannot",
    "i can't",
    "i refuse",
    "i'm unable",
    "i am unable",
    "i won't",
    "i will not",
)


def _parse_to_dict(raw: str):  # type: ignore[no-untyped-def]
    """Best-effort dict extraction from a judge's raw text.

    Returns:
      dict -- the parsed JSON object.
      "refusal" -- the prose around the JSON contained a refusal phrase
                   (caller treats this as score=0 with refusal reasoning).
      None -- no usable JSON object was found.

    Defensive design (codex review-round-5 fixes):
      * Strict `json.loads` may succeed and return a non-dict (list, str,
        number); we accept only dicts.
      * The brace-fallback now tries the LAST balanced `{...}` span,
        not the outer first-to-last slice, so a response with multiple
        JSON blocks (draft followed by final verdict) parses the final
        block rather than the unparseable concatenation.
    """
    stripped = raw.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Refusal check on the raw text first; if the surrounding prose
    # refuses, no embedded JSON should be trusted regardless of how
    # many balanced blocks we find.
    if any(phrase in raw.lower() for phrase in _REFUSAL_PHRASES):
        return "refusal"

    # Scan for balanced {...} blocks; try the LAST one first because
    # judges that "think aloud" emit the verdict at the end.
    blocks = _balanced_brace_blocks(raw)
    for block in reversed(blocks):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _balanced_brace_blocks(text: str) -> list[str]:
    """Return every balanced `{...}` block in `text`, in source order.

    Naive depth-counter: ignores strings/escapes (judges should not put
    raw `{` or `}` inside string values; if they do, the affected block
    is simply skipped). Adequate for the well-formed-JSON case we expect.
    """
    blocks: list[str] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    blocks.append(text[start : i + 1])
                    start = None
    return blocks


def parse_judge_response(raw: str, model: str) -> JudgeResult:
    """Pure: extract a JudgeResult from the judge's raw text.

    Tries strict JSON first. Falls back to scanning for the first
    well-formed JSON object in the response (handles judges that wrap
    JSON in prose despite the system prompt). Returns score=0.0 with
    a clear reasoning string when parsing fails entirely so the caller
    can surface the failure in the harness report rather than crashing.

    Refusal guard (adversarial review-round-5 finding): if the prose
    surrounding the JSON contains a refusal phrase, we return score=0
    with `is_infra_error=False` (this is a judge-quality signal, not
    infra) but the reasoning explicitly names the refusal so the
    operator does not interpret a hallucinated score as the agent's
    verdict.
    """
    data = _parse_to_dict(raw)
    if data is None:
        return JudgeResult(
            score=0.0,
            reasoning=(
                "judge response did not yield a JSON object with score "
                "and reasoning; raw response kept for debugging"
            ),
            raw_response=raw,
            model=model,
        )
    if data == "refusal":
        return JudgeResult(
            score=0.0,
            reasoning=(
                "judge response contained a refusal phrase outside "
                "the JSON block; embedded score is not trusted"
            ),
            raw_response=raw,
            model=model,
        )

    score_raw = data.get("score")
    reasoning = str(data.get("reasoning", "")).strip() or "(no reasoning)"
    if score_raw is None:
        return JudgeResult(
            score=0.0,
            reasoning="judge JSON object had no 'score' key",
            raw_response=raw,
            model=model,
        )
    try:
        score = float(score_raw)  # type: ignore[arg-type]  # justification: above None-guard narrows.
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


def get_threshold(trajectory) -> float:  # type: ignore[no-untyped-def]
    """Single-source threshold extraction (review-round-5 dedup).

    Callers in trajectory_harness.py and trajectory_verify.py both
    needed this exact logic: read llm_judge.threshold, coerce to float,
    fall back to 0.7 if missing or malformed. Centralizing here means
    a future ADR amendment to the default flows through one site.
    """
    threshold_raw = trajectory.llm_judge.get("threshold", 0.7)
    try:
        return float(threshold_raw)
    except (TypeError, ValueError):
        return 0.7


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
            # Codex review-round-5 #3: surface ALL tool arguments (not
            # just path-like keys) so rubrics that grade command text,
            # query strings, etc., have the evidence. Each value is
            # truncated to keep the summary under the judge's context.
            arg_bits: list[str] = []
            for key, value in event.arguments.items():
                if value is None:
                    continue
                text = repr(value)
                if len(text) > 200:
                    text = text[:197] + "..."
                arg_bits.append(f"{key}={text}")
            if arg_bits:
                suffix = " " + ", ".join(arg_bits)
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
