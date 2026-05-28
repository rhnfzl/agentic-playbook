"""Single source of truth for OTLP-span -> TelemetryRecord conversion.

Before this module the conversion existed twice:

  scripts/telemetry/pyotel_collector.py    _span_to_record, _redact, _attr_value
  scripts/telemetry/ingest.py              _coerce_record (OTLP branch), _otlp_value

The two implementations had small differences in attribute coverage
and severity of "missing attr" handling. Privacy guarantees lived in
the python collector's BANNED_PREFIXES tuple but not in the ingest
fallback parser. Bugs in one drifted from the other.

This module owns:

  ALLOWED_KEYS         attributes we keep in the record
  BANNED_PREFIXES      attributes we explicitly drop (privacy)
  extract_attribute    plucks a typed value from an OTel attribute
  redact_attributes    returns a redacted attrs dict (allowlist + banlist)
  span_to_record       OTLP span -> TelemetryRecord (or None)

Consumers should call `span_to_record`; the lower-level helpers are
exposed for tests and for the rare consumer that needs raw attrs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import TelemetryRecord


# Attribute keys we keep. Everything outside this allowlist is dropped
# before write or comparison.
ALLOWED_KEYS = frozenset({
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.prompt_tokens",   # legacy alias
    "gen_ai.usage.completion_tokens",  # legacy alias
    "gen_ai.agent.id",
    "gen_ai.agent.name",
    "gen_ai.query.source",
    "skill.name",
    "skill.id",
    "playbook.adapter",
})

# Banned keys we ACTIVELY strip even if the upstream sends them. The
# privacy guarantee in ADR-0048: no prompt or response body reaches
# disk. The collector pipeline (docker or pure-python) and the ingest
# fallback parser all use this list, so a future leak source is one
# `startswith` check away from being closed.
BANNED_PREFIXES = (
    "gen_ai.prompt",
    "gen_ai.choice",
    "gen_ai.input.message",
    "gen_ai.output.message",
    "gen_ai.completion",
)


def extract_attribute(value: object) -> object:
    """Pluck a typed value out of an OTLP attribute envelope.

    OTLP attribute values look like {"stringValue": "x"} or
    {"intValue": 42}. We unwrap the inner literal so callers do not
    need to know the OTLP shape. Returns None when the value is not
    a dict or carries no recognized type.
    """
    if not isinstance(value, dict):
        return None
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in value:
            return value[k]
    return None


def redact_attributes(attrs: list[dict] | None) -> dict[str, object]:
    """Return a redacted attribute dict: allowlist + banlist."""
    out: dict[str, object] = {}
    for attr in attrs or []:
        if not isinstance(attr, dict):
            continue
        key = attr.get("key", "")
        if not isinstance(key, str) or not key:
            continue
        if any(key.startswith(p) for p in BANNED_PREFIXES):
            continue
        if key not in ALLOWED_KEYS:
            continue
        out[key] = extract_attribute(attr.get("value", {}))
    return out


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def _as_str(value: object, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def span_to_record(span: object) -> TelemetryRecord | None:
    """Build a TelemetryRecord from an OTLP span if it carries a
    skill identifier. Returns None for spans that are not skill spans
    (e.g. nested HTTP spans, framework internals) or for non-dict
    inputs from a malformed envelope.
    """
    if not isinstance(span, dict):
        return None
    attrs = redact_attributes(span.get("attributes", []))
    skill = attrs.get("skill.name") or attrs.get("skill.id")
    if not isinstance(skill, str):
        return None
    start_ns = _as_int(span.get("startTimeUnixNano"))
    end_ns = _as_int(span.get("endTimeUnixNano"))
    latency_ms = (end_ns - start_ns) / 1_000_000 if end_ns > start_ns else 0.0
    fired_at = datetime.fromtimestamp(
        start_ns / 1_000_000_000 if start_ns > 0 else 0,
        tz=timezone.utc,
    ).isoformat(timespec="seconds")
    return TelemetryRecord(
        skill=skill,
        adapter=_as_str(
            attrs.get("playbook.adapter") or attrs.get("gen_ai.system"),
            "unknown",
        ),
        model=_as_str(
            attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model"),
            "unknown",
        ),
        fired_at=fired_at,
        latency_ms=latency_ms,
        input_tokens=_as_int(
            attrs.get("gen_ai.usage.input_tokens")
            or attrs.get("gen_ai.usage.prompt_tokens"),
        ),
        output_tokens=_as_int(
            attrs.get("gen_ai.usage.output_tokens")
            or attrs.get("gen_ai.usage.completion_tokens"),
        ),
    )
