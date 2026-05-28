"""Claude Code OTel trace shim (Phase 1, ADR-0045).

Claude Code emits OTel `gen_ai.*` spans natively when
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set. An OTel collector writes
those spans to a JSONL file (one span per line); this shim reads that
file and normalizes the spans into a TraceRecord.

Span attribute mapping (subset of code.claude.com/docs/en/monitoring-usage):

  gen_ai.operation.name=chat              -> kind=model_response;
                                             accumulates token usage.
  gen_ai.operation.name=tool_call         -> kind=tool_call; tool.name and
                                             tool.arguments captured.
  gen_ai.operation.name=skill_load        -> kind=skill_load; skill.name captured.
  gen_ai.request.model                    -> TraceRecord.model.
  gen_ai.usage.input_tokens               -> summed into total_input_tokens.
  gen_ai.usage.output_tokens              -> summed into total_output_tokens.

Unknown operation names are stored as raw_attrs with kind=model_response
so they survive the trace but do not affect the matcher.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from adapters.trace_record import TraceEvent, TraceRecord


def _attr_value(attr: dict) -> str | int | None:
    """Pull the scalar value out of an OTLP attribute entry."""
    value = attr.get("value", {})
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        try:
            return int(value["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in value:
        try:
            return float(value["doubleValue"])  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    if "boolValue" in value:
        return str(value["boolValue"])
    return None


def _attrs_to_dict(attrs: list[dict]) -> dict:
    """Convert OTLP `attributes` (list of {key, value}) into a flat dict."""
    out: dict = {}
    for attr in attrs:
        key = attr.get("key")
        if key is None:
            continue
        out[key] = _attr_value(attr)
    return out


def _sha256_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_otel_jsonl(
    path: Path,
    *,
    session_id: str,
    prompt: str,
) -> TraceRecord:
    """Read a Claude Code OTLP JSONL log and produce a TraceRecord.

    Malformed lines are skipped (not raised) so a single broken span
    does not poison the whole trace. The harness's report distinguishes
    `infra_fail` (parse-error rate above threshold) from
    `assertion_fail` so silent corruption is still visible.
    """
    raw_spans: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw_spans.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    raw_spans.sort(key=lambda s: int(s.get("startTimeUnixNano", "0") or 0))

    events: list[TraceEvent] = []
    artifacts: dict[str, str] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    model = "unknown"
    started_at_nano: int | None = None
    ended_at_nano: int | None = None

    for seq, span in enumerate(raw_spans):
        attrs = _attrs_to_dict(span.get("attributes", []))
        op = attrs.get("gen_ai.operation.name")

        start = int(span.get("startTimeUnixNano", "0") or 0)
        end = int(span.get("endTimeUnixNano", "0") or 0)
        duration_ms = max(0, (end - start) // 1_000_000) if end and start else None
        if started_at_nano is None or start < started_at_nano:
            started_at_nano = start
        if ended_at_nano is None or end > ended_at_nano:
            ended_at_nano = end

        if op == "chat":
            in_tokens = attrs.get("gen_ai.usage.input_tokens") or 0
            out_tokens = attrs.get("gen_ai.usage.output_tokens") or 0
            try:
                total_input_tokens += int(in_tokens)
                total_output_tokens += int(out_tokens)
            except (TypeError, ValueError):
                pass
            model_attr = attrs.get("gen_ai.request.model")
            if isinstance(model_attr, str) and model_attr:
                model = model_attr
            events.append(TraceEvent(
                seq=seq,
                kind="model_response",
                name=str(model_attr or "chat"),
                arguments=None,
                duration_ms=duration_ms,
                raw_attrs=attrs,
            ))
            continue

        if op == "tool_call":
            tool_name = attrs.get("tool.name") or span.get("name", "unknown")
            arguments_str = attrs.get("tool.arguments")
            arguments_dict: dict | None = None
            if isinstance(arguments_str, str):
                try:
                    arguments_dict = json.loads(arguments_str)
                except json.JSONDecodeError:
                    arguments_dict = {"raw": arguments_str}
            # Record any file write as an artifact.
            if (
                isinstance(tool_name, str)
                and tool_name == "Write"
                and isinstance(arguments_dict, dict)
            ):
                path_val = arguments_dict.get("path")
                content_val = arguments_dict.get("content", "")
                if isinstance(path_val, str) and isinstance(content_val, str):
                    artifacts[path_val] = _sha256_of(content_val)
            events.append(TraceEvent(
                seq=seq,
                kind="tool_call",
                name=str(tool_name),
                arguments=arguments_dict,
                duration_ms=duration_ms,
                raw_attrs=attrs,
            ))
            continue

        if op == "skill_load":
            skill_name = attrs.get("skill.name") or span.get("name", "unknown")
            events.append(TraceEvent(
                seq=seq,
                kind="skill_load",
                name=str(skill_name),
                arguments=None,
                duration_ms=duration_ms,
                raw_attrs=attrs,
            ))
            continue

        # Unknown operation: preserve as model_response with raw_attrs so the
        # matcher does not crash but a human can inspect.
        events.append(TraceEvent(
            seq=seq,
            kind="model_response",
            name=str(span.get("name", "unknown")),
            arguments=None,
            duration_ms=duration_ms,
            raw_attrs=attrs,
        ))

    started_at = (
        datetime.fromtimestamp(started_at_nano / 1e9, tz=timezone.utc)
        if started_at_nano
        else datetime.now(timezone.utc)
    )
    ended_at = (
        datetime.fromtimestamp(ended_at_nano / 1e9, tz=timezone.utc)
        if ended_at_nano
        else started_at
    )

    return TraceRecord(
        adapter="claude-code",
        model=model,
        session_id=session_id,
        prompt=prompt,
        events=events,
        artifacts=artifacts,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        started_at=started_at,
        ended_at=ended_at,
    )
