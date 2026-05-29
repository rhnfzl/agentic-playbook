"""Tests for telemetry JSONL ingest + per-skill aggregation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from telemetry import TelemetryRecord  # noqa: E402
from telemetry.ingest import (  # noqa: E402
    SkillAggregate,
    aggregate,
    filter_recent,
    read_jsonl,
)


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_read_jsonl_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "missing.jsonl") == []


def test_read_jsonl_parses_telemetry_record_shape(tmp_path: Path) -> None:
    p = _write_jsonl(
        tmp_path / "skills.jsonl",
        [
            {
                "skill": "to-prd",
                "adapter": "claude-code",
                "model": "claude-opus-4-7",
                "fired_at": "2026-05-28T12:00:00+00:00",
                "latency_ms": 1200.5,
                "input_tokens": 100,
                "output_tokens": 200,
            }
        ],
    )
    records = read_jsonl(p)
    assert len(records) == 1
    assert records[0].skill == "to-prd"
    assert records[0].latency_ms == 1200.5
    assert records[0].input_tokens == 100


def test_read_jsonl_tolerates_otlp_span_shape(tmp_path: Path) -> None:
    """Some collectors write raw OTLP spans; ingest should pluck attrs."""
    p = _write_jsonl(
        tmp_path / "skills.jsonl",
        [
            {
                "startTimeUnixNano": 1_700_000_000_000_000_000,
                "endTimeUnixNano": 1_700_000_001_500_000_000,
                "attributes": [
                    {"key": "skill.name", "value": {"stringValue": "to-prd"}},
                    {"key": "gen_ai.system", "value": {"stringValue": "claude-code"}},
                    {
                        "key": "gen_ai.response.model",
                        "value": {"stringValue": "claude-opus-4-7"},
                    },
                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 42}},
                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 84}},
                ],
            }
        ],
    )
    records = read_jsonl(p)
    assert len(records) == 1
    assert records[0].skill == "to-prd"
    assert records[0].input_tokens == 42
    assert records[0].latency_ms == 1500.0


def test_read_jsonl_skips_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "skills.jsonl"
    path.write_text("not-json\n{}\n", encoding="utf-8")
    assert read_jsonl(path) == []


def test_aggregate_groups_by_skill_and_orders_by_count() -> None:
    records = [
        TelemetryRecord("a", "cc", "m", "2026-05-28T10:00:00+00:00", 100, 1, 2),
        TelemetryRecord("a", "cc", "m", "2026-05-28T11:00:00+00:00", 200, 3, 4),
        TelemetryRecord("b", "cc", "m", "2026-05-28T12:00:00+00:00", 50, 5, 6),
    ]
    aggs = aggregate(records)
    assert len(aggs) == 2
    assert aggs[0].skill == "a" and aggs[0].trigger_count == 2
    assert aggs[1].skill == "b" and aggs[1].trigger_count == 1
    assert aggs[0].total_input_tokens == 4
    assert aggs[0].last_fired_at == "2026-05-28T11:00:00+00:00"


def test_aggregate_p50_p95_handle_single_value() -> None:
    records = [TelemetryRecord("a", "cc", "m", "2026-05-28T10:00:00+00:00", 500, 0, 0)]
    aggs = aggregate(records)
    assert aggs[0].p50_latency_ms == 500.0
    assert aggs[0].p95_latency_ms == 500.0


def test_filter_recent_keeps_only_records_in_window() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=5)).isoformat(timespec="seconds")
    stale = (now - timedelta(days=45)).isoformat(timespec="seconds")
    records = [
        TelemetryRecord("a", "cc", "m", fresh, 0, 0, 0),
        TelemetryRecord("b", "cc", "m", stale, 0, 0, 0),
    ]
    assert {r.skill for r in filter_recent(records, days=30)} == {"a"}
    assert len(filter_recent(records, days=0)) == 2


def test_aggregate_returns_skillaggregate_type() -> None:
    records = [TelemetryRecord("a", "cc", "m", "2026-05-28T10:00:00+00:00", 100, 1, 2)]
    aggs = aggregate(records)
    assert isinstance(aggs[0], SkillAggregate)


def test_read_jsonl_unwraps_otlp_resourcespan_envelope(tmp_path: Path) -> None:
    """The docker otelcol file exporter writes one envelope per line
    that wraps spans inside `resourceSpans -> scopeSpans -> spans`.
    Without unwrapping, every record would silently drop on the docker
    path (the entire docker collection path was effectively broken)."""
    path = _write_jsonl(
        tmp_path / "skills.jsonl",
        [
            {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "startTimeUnixNano": 1_700_000_000_000_000_000,
                                        "endTimeUnixNano": 1_700_000_001_000_000_000,
                                        "attributes": [
                                            {
                                                "key": "skill.name",
                                                "value": {"stringValue": "to-prd"},
                                            },
                                            {
                                                "key": "gen_ai.usage.input_tokens",
                                                "value": {"intValue": 50},
                                            },
                                        ],
                                    },
                                    {
                                        "startTimeUnixNano": 1_700_000_000_000_000_000,
                                        "endTimeUnixNano": 1_700_000_000_500_000_000,
                                        "attributes": [
                                            {
                                                "key": "skill.name",
                                                "value": {"stringValue": "code-review"},
                                            },
                                            {
                                                "key": "gen_ai.usage.input_tokens",
                                                "value": {"intValue": 25},
                                            },
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )
    records = read_jsonl(path)
    assert {r.skill for r in records} == {"to-prd", "code-review"}


def test_filter_recent_handles_naive_iso_timestamp() -> None:
    """Some collectors write timezone-naive timestamps. Without UTC
    coercion the comparison against `datetime.now(timezone.utc)`
    would shift by the local-time offset and could drop a freshly-
    fired record on systems where the offset is positive."""
    from datetime import datetime, timedelta, timezone

    naive_recent = (
        (datetime.now(timezone.utc) - timedelta(days=5))
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )
    records = [TelemetryRecord("a", "cc", "m", naive_recent, 0, 0, 0)]
    kept = filter_recent(records, days=30)
    assert len(kept) == 1, "naive ISO recent record should be kept"
