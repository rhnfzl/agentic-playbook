"""JSONL ingest + aggregation.

The collector (docker or pure-python) writes one JSON object per
line. This module reads those lines, normalizes them to
TelemetryRecord, and provides per-skill aggregates the report CLI
and the decay check both consume.

Both collectors write JSON in the TelemetryRecord shape directly,
so ingest is mostly a JSONL reader plus tolerance for the legacy
OTLP-span-as-line shape that the otelcol file exporter produces by
default.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable, NamedTuple

from . import TelemetryRecord, storage_path
from ._otlp_record import span_to_record


def _coerce_record(row: dict) -> TelemetryRecord | None:
    """Accept either a TelemetryRecord-shaped row or an OTLP span row
    and return TelemetryRecord. The OTLP path delegates to the shared
    `span_to_record` helper so the docker collector path and the
    pure-Python collector path produce identical records."""
    if "skill" in row and "fired_at" in row:
        try:
            return TelemetryRecord(
                skill=str(row["skill"]),
                adapter=str(row.get("adapter", "unknown")),
                model=str(row.get("model", "unknown")),
                fired_at=str(row["fired_at"]),
                latency_ms=float(row.get("latency_ms", 0)),
                input_tokens=int(row.get("input_tokens", 0)),
                output_tokens=int(row.get("output_tokens", 0)),
                session_id=str(row.get("session_id", "")),
            )
        except (TypeError, ValueError):
            return None
    return span_to_record(row)


def _records_from_row(row: dict) -> list[TelemetryRecord]:
    """One JSONL row may carry one TelemetryRecord, one raw OTLP span,
    OR a full OTLP envelope (resourceSpans -> scopeSpans -> spans)
    which the otelcol file exporter writes by default. Yield every
    record the row contains."""
    if "resourceSpans" in row:
        out: list[TelemetryRecord] = []
        for resource_span in row.get("resourceSpans", []) or []:
            if not isinstance(resource_span, dict):
                continue
            for scope_span in resource_span.get("scopeSpans", []) or []:
                if not isinstance(scope_span, dict):
                    continue
                for span in scope_span.get("spans", []) or []:
                    if not isinstance(span, dict):
                        continue
                    rec = _coerce_record(span)
                    if rec is not None:
                        out.append(rec)
        return out
    rec = _coerce_record(row)
    return [rec] if rec is not None else []


def read_jsonl(path: Path | None = None) -> list[TelemetryRecord]:
    """Read the JSONL file and return TelemetryRecord rows.

    Missing file is empty (no events recorded yet). Malformed lines
    are skipped silently; the collector is the source of truth, and
    a malformed line is the collector's bug, not the consumer's.

    Tolerates three row shapes: canonical TelemetryRecord (pure-Python
    collector), raw OTLP span (older otelcol versions), and OTLP
    envelope (`resourceSpans` -> `scopeSpans` -> `spans`) which the
    current otelcol file exporter writes by default.
    """
    p = path if path is not None else storage_path()
    if not p.is_file():
        return []
    out: list[TelemetryRecord] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            out.extend(_records_from_row(row))
    return out


class SkillAggregate(NamedTuple):
    """Per-skill rollup used by report + decay-by-usage."""

    skill: str
    trigger_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    last_fired_at: str
    adapters: tuple[str, ...]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def aggregate(records: Iterable[TelemetryRecord]) -> list[SkillAggregate]:
    """Group records by skill and produce per-skill aggregates."""
    bucket: dict[str, list[TelemetryRecord]] = {}
    for rec in records:
        bucket.setdefault(rec.skill, []).append(rec)
    out: list[SkillAggregate] = []
    for skill, rows in bucket.items():
        latencies = [r.latency_ms for r in rows]
        last_fired = max(r.fired_at for r in rows) if rows else ""
        adapters = sorted({r.adapter for r in rows})
        out.append(SkillAggregate(
            skill=skill,
            trigger_count=len(rows),
            p50_latency_ms=median(latencies) if latencies else 0.0,
            p95_latency_ms=_percentile(latencies, 95),
            total_input_tokens=sum(r.input_tokens for r in rows),
            total_output_tokens=sum(r.output_tokens for r in rows),
            last_fired_at=last_fired,
            adapters=tuple(adapters),
        ))
    out.sort(key=lambda a: a.trigger_count, reverse=True)
    return out


def filter_recent(records: Iterable[TelemetryRecord], days: int) -> list[TelemetryRecord]:
    """Keep records fired within the last `days` calendar days.

    Naive ISO timestamps (no `+00:00`) are coerced to UTC so the
    comparison against `datetime.now(timezone.utc)` does not shift
    by the local-time offset. Malformed strings drop the record.
    """
    if days <= 0:
        return list(records)
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    out: list[TelemetryRecord] = []
    for rec in records:
        try:
            parsed = datetime.fromisoformat(rec.fired_at)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed.timestamp() >= cutoff:
            out.append(rec)
    return out
