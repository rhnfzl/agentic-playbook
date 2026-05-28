"""DSL matcher (Phase 1, ADR-0046) — evaluates trajectory assertions against
a TraceRecord. Pure logic; no I/O, no LLM, no adapter-specific knowledge.

Each DSL primitive (first_skill_loaded, must_invoke_tool, etc.) gets a
direct test, plus the aggregator that combines them into a per-trace
pass/fail verdict.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _event(seq: int, kind: str, name: str, **extra):
    """Test helper: shorthand TraceEvent builder."""
    from adapters.trace_record import TraceEvent

    return TraceEvent(
        seq=seq,
        kind=kind,  # type: ignore[arg-type]  # justification: tests cover invalid kinds elsewhere
        name=name,
        arguments=extra.get("arguments"),
        duration_ms=extra.get("duration_ms"),
        raw_attrs=extra.get("raw_attrs", {}),
    )


def _trace(events: list, artifacts: dict | None = None, prompt: str = "test"):
    from adapters.trace_record import TraceRecord

    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="test-session",
        prompt=prompt,
        events=events,
        artifacts=artifacts or {},
        total_input_tokens=100,
        total_output_tokens=200,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


# --- first_skill_loaded ---


def test_first_skill_loaded_passes_when_correct() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "to-prd"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions([{"first_skill_loaded": "to-prd"}], trace)
    assert result.passed
    assert result.failures == []


def test_first_skill_loaded_fails_when_wrong_skill() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "brainstorming"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions([{"first_skill_loaded": "to-prd"}], trace)
    assert not result.passed
    assert any("first_skill_loaded" in f for f in result.failures)


def test_first_skill_loaded_fails_when_no_skill_loaded() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Write")])
    result = evaluate_assertions([{"first_skill_loaded": "to-prd"}], trace)
    assert not result.passed


# --- must_invoke_tool ---


def test_must_invoke_tool_passes_when_tool_called() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "tool_call", "Read"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions([{"must_invoke_tool": "Write"}], trace)
    assert result.passed


def test_must_invoke_tool_fails_when_tool_absent() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Read")])
    result = evaluate_assertions([{"must_invoke_tool": "Write"}], trace)
    assert not result.passed
    assert any("Write" in f for f in result.failures)


# --- must_not_invoke_tool ---


def test_must_not_invoke_tool_passes_when_tool_absent() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Write")])
    result = evaluate_assertions([{"must_not_invoke_tool": "Bash"}], trace)
    assert result.passed


def test_must_not_invoke_tool_fails_when_tool_called() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "tool_call", "Write"),
        _event(1, "tool_call", "Bash"),
    ])
    result = evaluate_assertions([{"must_not_invoke_tool": "Bash"}], trace)
    assert not result.passed


# --- final_artifact_path ---


def test_final_artifact_path_passes_when_glob_matches() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[_event(0, "tool_call", "Write", arguments={"path": "spec.md"})],
        artifacts={"spec.md": "sha256:abc"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert result.passed


def test_final_artifact_path_fails_when_glob_misses() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[_event(0, "tool_call", "Write", arguments={"path": "out.txt"})],
        artifacts={"out.txt": "sha256:abc"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert not result.passed


def test_final_artifact_path_fails_when_no_artifacts() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace(events=[_event(0, "tool_call", "Write")], artifacts={})
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert not result.passed


def test_final_artifact_path_uses_LAST_write_not_any(tmp_path) -> None:
    """Codex review finding: 'final' must mean LAST. A trace that writes
    draft.md then out.txt must fail `final_artifact_path: "*.md"`."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "draft.md"}),
            _event(1, "tool_call", "Write", arguments={"path": "out.txt"}),
        ],
        artifacts={"draft.md": "sha256:a", "out.txt": "sha256:b"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert not result.passed
    assert any("out.txt" in f for f in result.failures)


def test_final_artifact_path_passes_when_LAST_write_matches(tmp_path) -> None:
    """Opposite case: out.txt then draft.md -> last is .md -> pass."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "out.txt"}),
            _event(1, "tool_call", "Write", arguments={"path": "draft.md"}),
        ],
        artifacts={"out.txt": "sha256:a", "draft.md": "sha256:b"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert result.passed


def test_final_artifact_path_glob_does_not_cross_path_separator(tmp_path) -> None:
    """Third-review P2: `*.md` must NOT match `subdir/foo.md`. Python's
    stdlib `fnmatch.fnmatch` does (because `*` matches any character),
    but trajectory authors writing `*.md` expect basename-only matching.
    The matcher wraps fnmatch to enforce that contract."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "subdir/foo.md"}),
        ],
        artifacts={"subdir/foo.md": "sha256:a"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert not result.passed, (
        "`*.md` must not match `subdir/foo.md`; use `**/*.md` or `subdir/*.md`"
    )


def test_final_artifact_path_recursive_glob_crosses_separator(tmp_path) -> None:
    """Path-aware: patterns containing `/` use stdlib fnmatch against the
    full path. `subdir/*.md` matches `subdir/foo.md`."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "subdir/foo.md"}),
        ],
        artifacts={"subdir/foo.md": "sha256:a"},
    )
    result = evaluate_assertions(
        [{"final_artifact_path": "subdir/*.md"}], trace
    )
    assert result.passed


def test_final_artifact_path_normalizes_leading_dot_slash(tmp_path) -> None:
    """Codex review-round-4: `./foo.md` should match `*.md` (the leading
    `./` is path-equivalent to `foo.md`). Previously the leading `./`
    introduced a separator and the basename-style match rejected."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "./foo.md"}),
        ],
        artifacts={"./foo.md": "sha256:a"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert result.passed


def test_final_artifact_path_rejects_windows_backslash_separator(tmp_path) -> None:
    """Codex review-round-4: `subdir\\foo.md` (Windows-style separator)
    should NOT match `*.md`. Without normalization the backslash isn't
    a `/`, so the basename-style check would erroneously allow it."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace(
        events=[
            _event(0, "tool_call", "Write", arguments={"path": "subdir\\foo.md"}),
        ],
        artifacts={"subdir\\foo.md": "sha256:a"},
    )
    result = evaluate_assertions([{"final_artifact_path": "*.md"}], trace)
    assert not result.passed


# --- max_total_tool_calls / min_total_tool_calls ---


def test_max_total_tool_calls_passes_when_under_limit() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "tool_call", "Read"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions([{"max_total_tool_calls": 5}], trace)
    assert result.passed


def test_max_total_tool_calls_fails_when_over_limit() -> None:
    from trajectory_matcher import evaluate_assertions

    events = [_event(i, "tool_call", f"Tool{i}") for i in range(6)]
    trace = _trace(events)
    result = evaluate_assertions([{"max_total_tool_calls": 5}], trace)
    assert not result.passed


def test_min_total_tool_calls_fails_when_too_few() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Read")])
    result = evaluate_assertions([{"min_total_tool_calls": 3}], trace)
    assert not result.passed


# --- call_order ---


def test_call_order_passes_when_dependency_satisfied() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "tool_call", "AskUserQuestion"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions(
        [{"call_order": [{"tool": "AskUserQuestion", "before": "Write"}]}],
        trace,
    )
    assert result.passed


def test_call_order_fails_when_dependency_reversed() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "tool_call", "Write"),
        _event(1, "tool_call", "AskUserQuestion"),
    ])
    result = evaluate_assertions(
        [{"call_order": [{"tool": "AskUserQuestion", "before": "Write"}]}],
        trace,
    )
    assert not result.passed


def test_call_order_fails_when_required_tool_absent() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Write")])
    result = evaluate_assertions(
        [{"call_order": [{"tool": "AskUserQuestion", "before": "Write"}]}],
        trace,
    )
    assert not result.passed


# --- no_skill_load_after ---


def test_no_skill_load_after_passes_when_only_allowed_skills_load() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "to-prd"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions([{"no_skill_load_after": ["to-prd"]}], trace)
    assert result.passed


def test_no_skill_load_after_fails_when_unexpected_skill_loads() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "to-prd"),
        _event(1, "tool_call", "Write"),
        _event(2, "skill_load", "code-review"),
    ])
    result = evaluate_assertions([{"no_skill_load_after": ["to-prd"]}], trace)
    assert not result.passed


# --- unknown assertion key ---


def test_unknown_assertion_key_is_reported_not_silently_passed() -> None:
    """If a trajectory uses an unsupported assertion key (e.g. typo),
    the matcher must surface it — silently passing would mask bugs."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Write")])
    result = evaluate_assertions([{"definitely_not_a_real_key": "x"}], trace)
    assert not result.passed
    assert any("unknown" in f.lower() for f in result.failures)


# --- aggregation ---


def test_all_assertions_must_pass_for_overall_pass() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "to-prd"),
        _event(1, "tool_call", "Write"),
    ])
    result = evaluate_assertions(
        [
            {"first_skill_loaded": "to-prd"},
            {"must_invoke_tool": "Write"},
            {"must_not_invoke_tool": "Bash"},
        ],
        trace,
    )
    assert result.passed
    assert result.failures == []


def test_one_failing_assertion_fails_the_whole_result() -> None:
    from trajectory_matcher import evaluate_assertions

    trace = _trace([
        _event(0, "skill_load", "to-prd"),
        _event(1, "tool_call", "Bash"),
    ])
    result = evaluate_assertions(
        [
            {"first_skill_loaded": "to-prd"},
            {"must_not_invoke_tool": "Bash"},
        ],
        trace,
    )
    assert not result.passed
    assert len(result.failures) == 1


def test_empty_assertions_list_is_a_pass_by_construction() -> None:
    """The linter rejects empty assertions; if one slips through (overlay
    or external trajectory), the matcher passes vacuously rather than
    crashing. The linter is the gate, not the matcher."""
    from trajectory_matcher import evaluate_assertions

    trace = _trace([_event(0, "tool_call", "Write")])
    result = evaluate_assertions([], trace)
    assert result.passed
