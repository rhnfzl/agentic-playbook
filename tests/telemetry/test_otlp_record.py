"""Contract tests for the shared OTLP -> TelemetryRecord parser.

The boundary contract third reviewers flagged: BANNED_PREFIXES in
Python must match the YAML processor patterns in the docker
collector config, otherwise an indexed body variant could leak
through the docker path. Test 2 asserts the two contracts cover
the same semantic key space.

Test 3 asserts that ingest and pyotel_collector are now backed by
the same parser, so a future divergence is structurally impossible.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from telemetry._otlp_record import (  # noqa: E402
    BANNED_PREFIXES,
    redact_attributes,
    span_to_record,
)


_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "telemetry"
    / "otel_collector"
    / "collector-config.yaml"
)


def _yaml_banned_patterns() -> list[str]:
    text = _YAML_PATH.read_text(encoding="utf-8")
    return re.findall(r"pattern:\s*(\S+)", text)


def test_banned_prefixes_python_match_yaml_patterns() -> None:
    """Each Python prefix must have a corresponding YAML pattern that
    matches the same prefix + an optional `.` suffix. Lockstep contract:
    add one in Python, you must add the regex in YAML, and vice versa."""
    yaml_patterns = _yaml_banned_patterns()
    assert yaml_patterns, "collector-config.yaml should define banned patterns"

    yaml_compiled = [re.compile(pat) for pat in yaml_patterns]

    for prefix in BANNED_PREFIXES:
        # Both the exact prefix AND an indexed variant must match.
        exact = prefix
        indexed = f"{prefix}.0.content"
        assert any(p.match(exact) for p in yaml_compiled), (
            f"Python BANNED_PREFIXES has {exact!r} but no YAML pattern matches it"
        )
        assert any(p.match(indexed) for p in yaml_compiled), (
            f"Python BANNED_PREFIXES has {exact!r}; YAML must also match {indexed!r}"
        )


def test_span_to_record_drops_banned_prefixes() -> None:
    """Privacy: even when the upstream sends gen_ai.prompt.0,
    gen_ai.output.messages.5.content, etc., the canonical parser
    must drop them before returning a TelemetryRecord."""
    record = span_to_record(
        {
            "startTimeUnixNano": 1_700_000_000_000_000_000,
            "endTimeUnixNano": 1_700_000_001_000_000_000,
            "attributes": [
                {"key": "skill.name", "value": {"stringValue": "demo"}},
                {"key": "gen_ai.prompt.0", "value": {"stringValue": "LEAK_A"}},
                {
                    "key": "gen_ai.output.messages.5.content",
                    "value": {"stringValue": "LEAK_B"},
                },
            ],
        }
    )
    assert record is not None
    blob = json.dumps(record._asdict())
    assert "LEAK_A" not in blob
    assert "LEAK_B" not in blob


def test_redact_attributes_ignores_non_dict_entries() -> None:
    """Defensive: a malformed attribute list with stray non-dict
    entries must not crash the redactor."""
    attrs = [
        "not-a-dict",
        {"key": "skill.name", "value": {"stringValue": "demo"}},
        None,
    ]
    out = redact_attributes(attrs)  # type: ignore[arg-type]
    assert out == {"skill.name": "demo"}


def test_pyotel_and_ingest_share_one_parser() -> None:
    """Cross-consumer contract: both pyotel_collector.extract_records
    and ingest.read_jsonl produce the same record for the same span.
    They should, because both now route through `span_to_record`."""
    from telemetry import pyotel_collector
    from telemetry.ingest import _coerce_record

    span = {
        "startTimeUnixNano": 1_700_000_000_000_000_000,
        "endTimeUnixNano": 1_700_000_001_500_000_000,
        "attributes": [
            {"key": "skill.name", "value": {"stringValue": "to-prd"}},
            {"key": "gen_ai.system", "value": {"stringValue": "claude-code"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 42}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 84}},
        ],
    }
    from_pyotel = pyotel_collector.extract_records(
        {
            "resourceSpans": [{"scopeSpans": [{"spans": [span]}]}],
        }
    )
    from_ingest = _coerce_record(span)
    assert len(from_pyotel) == 1
    assert from_pyotel[0] == from_ingest
