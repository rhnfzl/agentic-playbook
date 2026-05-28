#!/usr/bin/env python3
"""Trajectory DSL matcher (Phase 1, ADR-0046).

Evaluates the deterministic-DSL half of a trajectory's assertions against
a TraceRecord. The LLM-judge half (Phase 2) is a separate module; this
file is pure logic, no LLM, no I/O, no adapter-specific knowledge.

Each DSL primitive is implemented as a small function returning either
None (pass) or a string explaining why it failed. The aggregator
`evaluate_assertions` runs every assertion against the trace and
returns a MatchResult.

Adding a new primitive:
  1. Add a function _check_<primitive>(value, trace) -> str | None.
  2. Register it in _PRIMITIVES below.
  3. Update ADR-0046's DSL surface and the trajectory linter's docs.
  4. Document it in base/trajectories/README.md.
"""

from __future__ import annotations

import fnmatch
from typing import Callable, NamedTuple

from adapters.trace_record import TraceRecord


class MatchResult(NamedTuple):
    """Per-trajectory match verdict.

    `passed` is True iff every assertion either passed OR had no opinion
    (vacuous-pass for empty assertion lists). `failures` carries one
    human-readable string per failed assertion so the harness report
    can attribute the failure precisely.
    """

    passed: bool
    failures: list[str]


# --- DSL primitives ---


def _check_first_skill_loaded(value: str, trace: TraceRecord) -> str | None:
    loads = trace.skill_loads()
    if not loads:
        return (
            f"first_skill_loaded: expected '{value}' but no skill_load events "
            f"appeared in the trace"
        )
    if loads[0].name != value:
        return (
            f"first_skill_loaded: expected '{value}', got '{loads[0].name}'"
        )
    return None


def _check_must_invoke_tool(value: str, trace: TraceRecord) -> str | None:
    if not any(e.name == value for e in trace.tool_calls()):
        return f"must_invoke_tool: '{value}' was never called"
    return None


def _check_must_not_invoke_tool(value: str, trace: TraceRecord) -> str | None:
    for call in trace.tool_calls():
        if call.name == value:
            return (
                f"must_not_invoke_tool: '{value}' was called "
                f"(at event seq={call.seq})"
            )
    return None


def _check_final_artifact_path(value: str, trace: TraceRecord) -> str | None:
    if not trace.artifacts:
        return (
            f"final_artifact_path: no artifacts were produced "
            f"(expected one matching '{value}')"
        )
    for path in trace.artifacts:
        if fnmatch.fnmatch(path, value):
            return None
    return (
        f"final_artifact_path: no artifact matches '{value}'. "
        f"Got: {sorted(trace.artifacts)}"
    )


def _check_max_total_tool_calls(value, trace: TraceRecord) -> str | None:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return f"max_total_tool_calls: '{value}' is not an integer"
    n = len(trace.tool_calls())
    if n > limit:
        return f"max_total_tool_calls: {n} tool calls exceeds limit of {limit}"
    return None


def _check_min_total_tool_calls(value, trace: TraceRecord) -> str | None:
    try:
        floor = int(value)
    except (TypeError, ValueError):
        return f"min_total_tool_calls: '{value}' is not an integer"
    n = len(trace.tool_calls())
    if n < floor:
        return f"min_total_tool_calls: {n} tool calls below floor of {floor}"
    return None


def _check_call_order(value, trace: TraceRecord) -> str | None:
    """value is a list of {tool: X, before: Y} dicts. For each, find the
    earliest seq of tool X and tool Y; assert seq(X) < seq(Y)."""
    if not isinstance(value, list):
        return f"call_order: expected list of dicts, got {type(value).__name__}"
    calls = trace.tool_calls()
    seq_by_name: dict[str, int] = {}
    for call in calls:
        seq_by_name.setdefault(call.name, call.seq)
    for entry in value:
        if not isinstance(entry, dict):
            return f"call_order: entry is not a dict: {entry!r}"
        tool = entry.get("tool")
        before = entry.get("before")
        if not tool or not before:
            return f"call_order: entry missing 'tool' or 'before': {entry!r}"
        if tool not in seq_by_name:
            return (
                f"call_order: '{tool}' must precede '{before}', "
                f"but '{tool}' was never called"
            )
        if before not in seq_by_name:
            return (
                f"call_order: '{tool}' must precede '{before}', "
                f"but '{before}' was never called"
            )
        if seq_by_name[tool] >= seq_by_name[before]:
            return (
                f"call_order: expected '{tool}' before '{before}'; "
                f"saw '{tool}' at seq={seq_by_name[tool]} and "
                f"'{before}' at seq={seq_by_name[before]}"
            )
    return None


def _check_no_skill_load_after(value, trace: TraceRecord) -> str | None:
    """value is a list of allowed skill names. Any skill_load event whose
    name is not in the allowed list is a failure."""
    if not isinstance(value, list):
        return f"no_skill_load_after: expected list of allowed skill slugs"
    allowed = set(value)
    for event in trace.skill_loads():
        if event.name not in allowed:
            return (
                f"no_skill_load_after: skill '{event.name}' loaded at "
                f"seq={event.seq}; allowed set is {sorted(allowed)}"
            )
    return None


# Registry: assertion key -> (value, trace) -> failure msg | None.
# Order is preserved for stable report output.
_PRIMITIVES: dict[str, Callable[[object, TraceRecord], "str | None"]] = {
    "first_skill_loaded": _check_first_skill_loaded,  # type: ignore[dict-item]
    "must_invoke_tool": _check_must_invoke_tool,  # type: ignore[dict-item]
    "must_not_invoke_tool": _check_must_not_invoke_tool,  # type: ignore[dict-item]
    "final_artifact_path": _check_final_artifact_path,  # type: ignore[dict-item]
    "max_total_tool_calls": _check_max_total_tool_calls,
    "min_total_tool_calls": _check_min_total_tool_calls,
    "call_order": _check_call_order,
    "no_skill_load_after": _check_no_skill_load_after,
}


def evaluate_assertions(
    assertions: list[dict],
    trace: TraceRecord,
) -> MatchResult:
    """Run every assertion against the trace; aggregate into a MatchResult.

    Each assertion is a single-key dict (e.g. `{"must_invoke_tool": "Write"}`).
    Unknown keys are reported as failures, not silently passed: a typo in
    a trajectory should surface, not green CI.
    """
    failures: list[str] = []
    for assertion in assertions:
        if not isinstance(assertion, dict) or len(assertion) != 1:
            failures.append(
                f"malformed assertion (must be a single-key dict): {assertion!r}"
            )
            continue
        key, value = next(iter(assertion.items()))
        check = _PRIMITIVES.get(key)
        if check is None:
            failures.append(
                f"unknown assertion key '{key}'; known: {sorted(_PRIMITIVES)}"
            )
            continue
        failure = check(value, trace)
        if failure is not None:
            failures.append(failure)
    return MatchResult(passed=not failures, failures=failures)
