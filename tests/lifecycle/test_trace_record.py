"""TraceRecord + TraceEvent shape (Phase 1, ADR-0045).

The TraceRecord is the cross-adapter contract: every trace shim
(Claude Code, Codex, Cursor, Windsurf) normalizes its native trace
output into this shape so the matcher consumes one structure.

Pure data. No I/O, no LLM, no adapter-specific knowledge.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_trace_event_required_fields() -> None:
    from adapters.trace_record import TraceEvent

    fields = TraceEvent._fields
    assert "seq" in fields
    assert "kind" in fields
    assert "name" in fields
    assert "arguments" in fields
    assert "duration_ms" in fields
    assert "raw_attrs" in fields


def test_trace_event_kinds_are_constrained() -> None:
    """Allowed event kinds (Literal): skill_load, tool_call, tool_result,
    model_response. Anything else is a shim bug."""
    from adapters.trace_record import TRACE_EVENT_KINDS

    assert "skill_load" in TRACE_EVENT_KINDS
    assert "tool_call" in TRACE_EVENT_KINDS
    assert "tool_result" in TRACE_EVENT_KINDS
    assert "model_response" in TRACE_EVENT_KINDS
    assert len(TRACE_EVENT_KINDS) == 4


def test_trace_record_required_fields() -> None:
    from adapters.trace_record import TraceRecord

    fields = TraceRecord._fields
    assert "adapter" in fields
    assert "model" in fields
    assert "session_id" in fields
    assert "prompt" in fields
    assert "events" in fields
    assert "artifacts" in fields
    assert "total_input_tokens" in fields
    assert "total_output_tokens" in fields
    assert "started_at" in fields
    assert "ended_at" in fields


def test_trace_record_can_be_constructed() -> None:
    from adapters.trace_record import TraceEvent, TraceRecord

    rec = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="abc-123",
        prompt="Help me write a PRD",
        events=[
            TraceEvent(
                seq=0,
                kind="skill_load",
                name="to-prd",
                arguments=None,
                duration_ms=None,
                raw_attrs={},
            ),
            TraceEvent(
                seq=1,
                kind="tool_call",
                name="Write",
                arguments={"path": "spec.md"},
                duration_ms=12,
                raw_attrs={"gen_ai.operation.name": "tool_call"},
            ),
        ],
        artifacts={"spec.md": "sha256:abc123"},
        total_input_tokens=150,
        total_output_tokens=420,
        started_at=datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, 10, 1, tzinfo=timezone.utc),
    )
    assert rec.adapter == "claude-code"
    assert len(rec.events) == 2
    assert rec.events[0].kind == "skill_load"
    assert rec.events[1].name == "Write"
    assert rec.artifacts["spec.md"] == "sha256:abc123"


def test_trace_record_tool_call_helper() -> None:
    """Convenience accessor: tool_calls() returns only tool_call events."""
    from adapters.trace_record import TraceEvent, TraceRecord

    rec = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="skill_load", name="to-prd",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Read",
                       arguments=None, duration_ms=5, raw_attrs={}),
            TraceEvent(seq=2, kind="tool_result", name="Read",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=3, kind="tool_call", name="Write",
                       arguments=None, duration_ms=8, raw_attrs={}),
        ],
        artifacts={},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    calls = rec.tool_calls()
    assert [e.name for e in calls] == ["Read", "Write"]


def test_trace_record_skill_loads_helper() -> None:
    """Convenience accessor: skill_loads() returns only skill_load events."""
    from adapters.trace_record import TraceEvent, TraceRecord

    rec = TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="s",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="skill_load", name="to-prd",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Write",
                       arguments=None, duration_ms=8, raw_attrs={}),
            TraceEvent(seq=2, kind="skill_load", name="brainstorming",
                       arguments=None, duration_ms=None, raw_attrs={}),
        ],
        artifacts={},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    loads = rec.skill_loads()
    assert [e.name for e in loads] == ["to-prd", "brainstorming"]


def test_trace_record_known_adapter_validation() -> None:
    """The adapter name is constrained to the known set."""
    from adapters.trace_record import KNOWN_TRACE_ADAPTERS

    assert KNOWN_TRACE_ADAPTERS == {"claude-code", "codex", "cursor", "windsurf"}
