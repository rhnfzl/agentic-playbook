"""Claude Code OTel trace shim (Phase 1, ADR-0045).

Capture contract:

  This shim accepts EITHER of two on-disk formats per the OpenTelemetry
  spec, and flattens transparently:

  Format A (Node ConsoleSpanExporter output): one flat span object per
  line, no envelope. Produced by:

      OTEL_TRACES_EXPORTER=console claude code <session>
        > trace.jsonl 2>&1

  Format B (OTLP-over-HTTP/JSON envelope): nested
  `resourceSpans -> scopeSpans -> spans` per the OpenTelemetry proto.
  Produced when an `otelcol` HTTP receiver is configured with
  `OTEL_TRACES_EXPORTER=otlp` and a file_exporter sink. Each line is
  one envelope; the shim flattens the nested span list before parsing.

  Both formats survive the same downstream pipeline because the
  TraceEvent contract is identical for either source.

Span attribute mapping (subset of code.claude.com/docs/en/monitoring-usage):

  gen_ai.operation.name=chat              -> kind=model_response;
                                             accumulates token usage.
  gen_ai.operation.name=tool_call         -> kind=tool_call; tool.name and
                                             tool.arguments captured. Write,
                                             Edit, NotebookEdit produce
                                             artifact entries (Write hashes
                                             the content; Edit/NotebookEdit
                                             record the file path with an
                                             `edit:` sentinel since the
                                             post-edit hash is not in the
                                             tool input).
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


def _flatten_envelope(parsed: dict) -> list[dict]:
    """Return the list of span dicts inside `parsed`.

    Accepts both the flat shape (parsed IS a span) and the nested OTLP
    envelope shape (resourceSpans -> scopeSpans -> spans). Returns an
    empty list when neither shape is recognized; the caller skips and
    the surrounding loop continues to the next line.
    """
    # Flat span: has the marker attributes the parser needs.
    if "startTimeUnixNano" in parsed or "attributes" in parsed:
        return [parsed]
    # Nested OTLP envelope.
    spans: list[dict] = []
    for resource_span in parsed.get("resourceSpans", []) or []:
        if not isinstance(resource_span, dict):
            continue
        for scope_span in resource_span.get("scopeSpans", []) or []:
            if not isinstance(scope_span, dict):
                continue
            for span in scope_span.get("spans", []) or []:
                if isinstance(span, dict):
                    spans.append(span)
    return spans


def parse_otel_jsonl(
    path: Path,
    *,
    session_id: str,
    prompt: str,
) -> TraceRecord:
    """Read a Claude Code OTLP JSONL log and produce a TraceRecord.

    Accepts flat-per-line spans (console exporter) or nested OTLP
    envelopes (`resourceSpans -> scopeSpans -> spans`). Malformed lines
    are skipped (not raised) so a single broken span does not poison
    the whole trace. The harness report distinguishes infra failures
    from assertion failures so silent corruption stays visible.
    """
    raw_spans: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            raw_spans.extend(_flatten_envelope(parsed))

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
            # Record file-producing tools as artifacts. Write hashes content
            # because it is present in the tool input. Edit and NotebookEdit
            # use an `edit:` sentinel because the post-edit file content is
            # not in the tool input; the path glob in `final_artifact_path`
            # still matches, so trajectories that assert "*.py was touched"
            # work for both create and modify operations.
            if isinstance(tool_name, str) and isinstance(arguments_dict, dict):
                path_val = (
                    arguments_dict.get("path")
                    or arguments_dict.get("file_path")
                    or arguments_dict.get("notebook_path")
                )
                if isinstance(path_val, str):
                    if tool_name == "Write":
                        content_val = arguments_dict.get("content", "")
                        if isinstance(content_val, str):
                            artifacts[path_val] = _sha256_of(content_val)
                    elif tool_name in {"Edit", "NotebookEdit"}:
                        # Sentinel; the file existed before this tool ran and
                        # the post-edit hash is not in the tool input.
                        artifacts.setdefault(path_val, f"edit:{tool_name}")
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
