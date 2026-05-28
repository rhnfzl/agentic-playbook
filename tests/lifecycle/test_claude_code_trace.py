"""Claude Code OTel trace shim (Phase 1).

Claude Code emits OTel `gen_ai.*` spans natively (one OTLP env var
away). The shim consumes the JSONL collector output and produces a
TraceRecord per session.

These tests drive fixtures, not a live agent. The fixture format is the
OTLP-over-HTTP/JSON payload that an OTel collector writes when
configured with `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _write_otel_jsonl(tmp_path: Path, lines: list[dict]) -> Path:
    """Write a fixture file with one OTLP span per line."""
    out = tmp_path / "traces.jsonl"
    out.write_text("\n".join(json.dumps(ln) for ln in lines), encoding="utf-8")
    return out


# Minimal OTLP span shape (subset of the spec; only what the shim needs).
def _span(
    name: str,
    attributes: dict | None = None,
    start_unix_nano: int = 1717000000000000000,
    end_unix_nano: int = 1717000000010000000,
) -> dict:
    attrs = attributes or {}
    return {
        "name": name,
        "startTimeUnixNano": str(start_unix_nano),
        "endTimeUnixNano": str(end_unix_nano),
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)} if not isinstance(v, int) else {"intValue": str(v)}}
            for k, v in attrs.items()
        ],
    }


def test_shim_returns_empty_trace_for_empty_jsonl(tmp_path: Path) -> None:
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(tmp_path, [])
    record = parse_otel_jsonl(out, session_id="s1", prompt="hello")
    assert record.adapter == "claude-code"
    assert record.session_id == "s1"
    assert record.prompt == "hello"
    assert record.events == []
    assert record.artifacts == {}


def test_shim_parses_tool_call_span(tmp_path: Path) -> None:
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(
        tmp_path,
        [_span("Write", attributes={
            "gen_ai.operation.name": "tool_call",
            "tool.name": "Write",
            "tool.arguments": '{"path": "spec.md"}',
        })],
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    calls = record.tool_calls()
    assert len(calls) == 1
    assert calls[0].name == "Write"
    assert calls[0].arguments == {"path": "spec.md"}


def test_shim_parses_skill_load_span(tmp_path: Path) -> None:
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(
        tmp_path,
        [_span("skill_load", attributes={
            "gen_ai.operation.name": "skill_load",
            "skill.name": "to-prd",
        })],
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    loads = record.skill_loads()
    assert len(loads) == 1
    assert loads[0].name == "to-prd"


def test_shim_preserves_seq_order(tmp_path: Path) -> None:
    """Events should be ordered by start time."""
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(
        tmp_path,
        [
            _span(
                "tool_call",
                attributes={"gen_ai.operation.name": "tool_call", "tool.name": "Write"},
                start_unix_nano=2000,
                end_unix_nano=3000,
            ),
            _span(
                "skill_load",
                attributes={"gen_ai.operation.name": "skill_load", "skill.name": "to-prd"},
                start_unix_nano=1000,
                end_unix_nano=1500,
            ),
        ],
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    # skill_load (start=1000) before tool_call (start=2000)
    assert record.events[0].kind == "skill_load"
    assert record.events[0].seq == 0
    assert record.events[1].kind == "tool_call"
    assert record.events[1].seq == 1


def test_shim_accumulates_token_usage(tmp_path: Path) -> None:
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(
        tmp_path,
        [
            _span("inference", attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": "claude-opus-4-7",
                "gen_ai.usage.input_tokens": 50,
                "gen_ai.usage.output_tokens": 100,
            }),
            _span("inference", attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": "claude-opus-4-7",
                "gen_ai.usage.input_tokens": 60,
                "gen_ai.usage.output_tokens": 120,
            }),
        ],
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    assert record.total_input_tokens == 110
    assert record.total_output_tokens == 220
    assert record.model == "claude-opus-4-7"


def test_shim_records_artifacts_from_write_calls(tmp_path: Path) -> None:
    from adapters.claude_code_trace import parse_otel_jsonl

    out = _write_otel_jsonl(
        tmp_path,
        [_span("Write", attributes={
            "gen_ai.operation.name": "tool_call",
            "tool.name": "Write",
            "tool.arguments": '{"path": "spec.md", "content": "# Hello"}',
        })],
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    assert "spec.md" in record.artifacts
    # sha256 of "# Hello"
    assert record.artifacts["spec.md"].startswith("sha256:")


def test_shim_handles_malformed_jsonl_gracefully(tmp_path: Path) -> None:
    """One bad line should not poison the whole trace."""
    from adapters.claude_code_trace import parse_otel_jsonl

    out = tmp_path / "traces.jsonl"
    out.write_text(
        "not json\n" + json.dumps(_span("Write", attributes={
            "gen_ai.operation.name": "tool_call",
            "tool.name": "Write",
        })),
        encoding="utf-8",
    )
    record = parse_otel_jsonl(out, session_id="s1", prompt="x")
    assert len(record.tool_calls()) == 1
