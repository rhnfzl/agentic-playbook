"""Tests for the pure-Python OTLP collector.

Two contracts to verify:
  1. Span extraction is correct (TelemetryRecord shape, attribute
     plucking).
  2. Privacy: prompt/response bodies are NEVER written to disk even
     when present in the input envelope.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from telemetry.pyotel_collector import (  # noqa: E402
    BANNED_PREFIXES,
    append_records,
    extract_records,
)


def _envelope(attributes: list[dict]) -> dict:
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "startTimeUnixNano": 1_700_000_000_000_000_000,
                                "endTimeUnixNano": 1_700_000_001_000_000_000,
                                "attributes": attributes,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_extract_pulls_skill_record() -> None:
    env = _envelope(
        [
            {"key": "skill.name", "value": {"stringValue": "to-prd"}},
            {"key": "gen_ai.system", "value": {"stringValue": "claude-code"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 100}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 200}},
        ]
    )
    records = extract_records(env)
    assert len(records) == 1
    rec = records[0]
    assert rec.skill == "to-prd"
    assert rec.input_tokens == 100
    assert rec.output_tokens == 200
    assert rec.latency_ms == 1000.0


def test_extract_skips_spans_without_skill_attribute() -> None:
    env = _envelope(
        [
            {"key": "gen_ai.system", "value": {"stringValue": "claude-code"}},
        ]
    )
    assert extract_records(env) == []


def test_privacy_banned_prefixes_are_dropped() -> None:
    """Even when the envelope ships gen_ai.prompt, gen_ai.choice,
    etc., the extractor must not surface them."""
    env = _envelope(
        [
            {"key": "skill.name", "value": {"stringValue": "to-prd"}},
            {"key": "gen_ai.prompt", "value": {"stringValue": "USER SECRET"}},
            {"key": "gen_ai.choice", "value": {"stringValue": "RESPONSE BODY"}},
            {
                "key": "gen_ai.input.messages.0.content",
                "value": {"stringValue": "leaky"},
            },
            {
                "key": "gen_ai.output.messages.0.content",
                "value": {"stringValue": "leaky"},
            },
        ]
    )
    records = extract_records(env)
    assert len(records) == 1
    # The record is a NamedTuple with fixed fields; no body field exists.
    assert "USER SECRET" not in repr(records[0])
    assert "RESPONSE BODY" not in repr(records[0])


def test_banned_prefixes_includes_canonical_body_keys() -> None:
    for key in (
        "gen_ai.prompt",
        "gen_ai.choice",
        "gen_ai.input.message",
        "gen_ai.output.message",
        "gen_ai.completion",
    ):
        assert key in BANNED_PREFIXES


def test_indexed_otel_variants_are_dropped() -> None:
    """Real-world OTel SDKs emit keys like gen_ai.input.messages.0.content
    and gen_ai.completion.text. The collector must strip them too, not
    only the exact prefix names. Without this guarantee the docker path
    would let prompt bodies through (ADR-0048 reject-if criterion)."""
    env = _envelope(
        [
            {"key": "skill.name", "value": {"stringValue": "to-prd"}},
            {
                "key": "gen_ai.input.messages.0.content",
                "value": {"stringValue": "LEAKY USER PROMPT 0"},
            },
            {
                "key": "gen_ai.input.messages.1.content",
                "value": {"stringValue": "LEAKY USER PROMPT 1"},
            },
            {
                "key": "gen_ai.output.messages.0.content",
                "value": {"stringValue": "LEAKY RESPONSE 0"},
            },
            {
                "key": "gen_ai.completion.text",
                "value": {"stringValue": "LEAKY COMPLETION"},
            },
            {
                "key": "gen_ai.choice.0.message.content",
                "value": {"stringValue": "LEAKY CHOICE"},
            },
            {"key": "gen_ai.prompt.0", "value": {"stringValue": "LEAKY PROMPT"}},
        ]
    )
    records = extract_records(env)
    assert len(records) == 1
    blob = repr(records[0])
    for needle in (
        "LEAKY USER PROMPT",
        "LEAKY RESPONSE",
        "LEAKY COMPLETION",
        "LEAKY CHOICE",
        "LEAKY PROMPT",
    ):
        assert needle not in blob


def test_append_records_writes_jsonl(tmp_path: Path) -> None:
    from telemetry import TelemetryRecord

    out = tmp_path / "skills.jsonl"
    append_records(
        [
            TelemetryRecord("a", "cc", "m", "2026-05-28T00:00:00+00:00", 1.0, 1, 2),
        ],
        out,
    )
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["skill"] == "a"


def test_append_records_appends_not_truncates(tmp_path: Path) -> None:
    from telemetry import TelemetryRecord

    out = tmp_path / "skills.jsonl"
    append_records(
        [
            TelemetryRecord("a", "cc", "m", "2026-05-28T00:00:00+00:00", 1.0, 1, 2),
        ],
        out,
    )
    append_records(
        [
            TelemetryRecord("b", "cc", "m", "2026-05-28T00:00:00+00:00", 1.0, 1, 2),
        ],
        out,
    )
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["skill"] for r in rows] == ["a", "b"]
