"""Pure-Python OTLP/HTTP collector.

Minimal stdlib-only receiver for users who do not want a docker
dependency. Listens on localhost:4318 (the OTLP/HTTP default), reads
POSTed protobuf-or-JSON traces, extracts the gen_ai.* attributes we
care about, and appends one TelemetryRecord JSONL line per skill
span.

Out of scope: protobuf parsing. Claude Code's OTel exporter can be
configured to send JSON envelopes via
`OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json` which is what we
accept here. If a user has only the protobuf-default exporter, the
docker-compose collector under otel_collector/ accepts both.

Privacy: prompt and response bodies (`gen_ai.prompt`, `gen_ai.choice`,
`gen_ai.input.messages`, `gen_ai.output.messages`) are silently
dropped. Only metadata reaches the JSONL file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Direct invocation (`python3 scripts/telemetry/pyotel_collector.py` per
# the documented no-docker path) has no package context, so the relative
# import would raise ImportError before argparse runs. Bootstrap the
# scripts/ directory onto sys.path and use an absolute import; the
# module is still importable as `telemetry.pyotel_collector` from inside
# the package, so this does not break `python -m` use.
_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from telemetry import (  # noqa: E402
    DEFAULT_TELEMETRY_DIR,
    JSONL_FILENAME,
    TelemetryRecord,
    is_enabled,
    storage_path,
)


# Attribute keys we extract from `gen_ai.*` conventions. Anything outside
# this allowlist is dropped before write.
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

# Banned keys we ACTIVELY strip even if the upstream sends them. This is
# the privacy guarantee: prompt and response bodies must not reach disk.
BANNED_PREFIXES = (
    "gen_ai.prompt",
    "gen_ai.choice",
    "gen_ai.input.message",
    "gen_ai.output.message",
    "gen_ai.completion",
)


def _attr_value(attr: dict) -> object:
    value = attr.get("value", {}) if isinstance(attr, dict) else {}
    if not isinstance(value, dict):
        return None
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in value:
            return value[k]
    return None


def _redact(attrs: list[dict] | None) -> dict:
    """Return a redacted attribute dict: only ALLOWED_KEYS, never BANNED."""
    out: dict = {}
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
        out[key] = _attr_value(attr)
    return out


def _span_to_record(span: dict) -> TelemetryRecord | None:
    """Build a TelemetryRecord from an OTLP span if it is a skill span."""
    attrs = _redact(span.get("attributes", []))
    skill = attrs.get("skill.name") or attrs.get("skill.id")
    if not isinstance(skill, str):
        return None
    start_ns = int(span.get("startTimeUnixNano", 0) or 0)
    end_ns = int(span.get("endTimeUnixNano", 0) or 0)
    latency_ms = (end_ns - start_ns) / 1_000_000 if end_ns > start_ns else 0.0
    fired_at = datetime.fromtimestamp(
        start_ns / 1_000_000_000 if start_ns > 0 else 0,
        tz=timezone.utc,
    ).isoformat(timespec="seconds")
    input_tokens = int(
        attrs.get("gen_ai.usage.input_tokens")
        or attrs.get("gen_ai.usage.prompt_tokens")
        or 0
    )
    output_tokens = int(
        attrs.get("gen_ai.usage.output_tokens")
        or attrs.get("gen_ai.usage.completion_tokens")
        or 0
    )
    model = str(
        attrs.get("gen_ai.response.model")
        or attrs.get("gen_ai.request.model")
        or "unknown"
    )
    adapter = str(attrs.get("playbook.adapter") or attrs.get("gen_ai.system") or "unknown")
    return TelemetryRecord(
        skill=skill,
        adapter=adapter,
        model=model,
        fired_at=fired_at,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def extract_records(envelope: dict) -> list[TelemetryRecord]:
    """Walk an OTLP/HTTP JSON envelope and return TelemetryRecords.

    Public for tests. Mirrors the trajectory harness OTel parser
    layout (resourceSpans → scopeSpans → spans).
    """
    records: list[TelemetryRecord] = []
    for resource_span in envelope.get("resourceSpans", []) or []:
        for scope_span in resource_span.get("scopeSpans", []) or []:
            for span in scope_span.get("spans", []) or []:
                rec = _span_to_record(span)
                if rec is not None:
                    records.append(rec)
    return records


def append_records(records: list[TelemetryRecord], path: Path) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec._asdict()) + "\n")


class _Handler(BaseHTTPRequestHandler):
    storage: Path = DEFAULT_TELEMETRY_DIR / JSONL_FILENAME

    def do_POST(self) -> None:  # noqa: N802 (http handler shape)
        if self.path != "/v1/traces":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        try:
            envelope = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        records = extract_records(envelope if isinstance(envelope, dict) else {})
        append_records(records, type(self).storage)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted":true}')

    def log_message(self, format: str, *args) -> None:  # noqa: A002 (http shape)
        pass


def serve(host: str = "127.0.0.1", port: int = 4318, *, output: Path | None = None) -> None:
    if output is not None:
        _Handler.storage = output
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"  ok  pyotel collector listening on http://{host}:{port}/v1/traces")
    print(f"      writing to {_Handler.storage}")
    print("      Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  ok  pyotel collector stopped")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4318)
    parser.add_argument(
        "--output", type=Path, default=None,
        help=f"defaults to {storage_path()}",
    )
    args = parser.parse_args(argv)

    if not is_enabled():
        print("  .  telemetry disabled (TELEMETRY=off); refusing to start collector")
        return 0

    output = args.output or storage_path()
    serve(args.host, args.port, output=output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
