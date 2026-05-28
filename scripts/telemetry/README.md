# scripts/telemetry/

The opt-in OpenTelemetry collector + per-skill reporting + usage-decay integration. Per ADR-0048.

## What ships here

| File | Role |
|---|---|
| `__init__.py` | Public exports: `TelemetryRecord`, `is_enabled`, `storage_path`, constants (`DEFAULT_TELEMETRY_DIR`, `JSONL_FILENAME`). |
| `_otlp_record.py` | Canonical OTLP-span → TelemetryRecord parser. Single source of truth shared by every consumer (collector, ingest, reports). Enforces the banned-prefix privacy contract. |
| `pyotel_collector.py` | Stdlib-only OTLP/HTTP receiver. Listens on `localhost:4318`, accepts JSON-shaped OTLP envelopes, redacts banned prefixes, appends JSONL. No docker required. |
| `ingest.py` | JSONL → aggregated records reader. Tolerates raw OTLP spans, resourceSpans envelopes, and pre-parsed TelemetryRecord shapes. |
| `otel_collector/` | Docker-compose recipe for the standard `otelcol` binary as an alternative to `pyotel_collector.py`. Includes `collector-config.yaml` with the privacy redactions in YAML processor form. |

## How `make telemetry-report` consumes this

```
  make telemetry-report → scripts/skill_telemetry_report.py
                              │
                              └─ telemetry/ingest.py
                                   ├─ read_jsonl(<jsonl path>)
                                   ├─ _coerce_record() / _records_from_row()
                                   ├─ aggregate(records) → SkillAggregate per skill
                                   └─ filter_recent(records, days=30)
```

## How to enable (default off)

```bash
export TELEMETRY=on

# Option A: stdlib collector, no docker required.
python3 scripts/telemetry/pyotel_collector.py
# Now point Claude Code's OTel exporter at http://localhost:4318/v1/traces.

# Option B: docker-compose collector with the standard otelcol binary.
cd scripts/telemetry/otel_collector
docker-compose up
```

Both write to `~/.coding-agents-playbook/telemetry/skills.jsonl` by default. Override with `TELEMETRY_DIR=<path>` or the collector's `--output` flag.

## Privacy

**No prompt bodies or response bodies are ever stored.** The collector silently drops these attributes before writing JSONL:

```
gen_ai.prompt
gen_ai.choice
gen_ai.input.messages
gen_ai.output.messages
gen_ai.completion
```

The privacy contract is enforced in two places that MUST agree (or one bypass would leak):

1. Python side: `BANNED_PREFIXES` in `_otlp_record.py`. The pyotel collector + ingest both delegate to `span_to_record()` here.
2. YAML side: regex patterns in `otel_collector/collector-config.yaml`. The docker otelcol drops the same prefixes via YAML processors.

A boundary test (`tests/telemetry/test_otlp_record.py::test_banned_prefixes_python_match_yaml_patterns`) reads the YAML config, extracts the prefix patterns, and asserts every Python `BANNED_PREFIXES` entry has a corresponding YAML pattern covering both the exact key and an indexed variant (`gen_ai.prompt.0.content`). Adding a prefix in one side and forgetting the other fails CI.

## What gets recorded

Per-skill spans only. Each TelemetryRecord has:

```python
@dataclass(frozen=True)
class TelemetryRecord:
    skill: str           # canonical skill identity (per scripts/skill_identity.py)
    adapter: str         # claude-code / codex / cursor / windsurf
    model: str           # e.g. claude-opus-4-7
    fired_at: str        # ISO 8601 UTC
    latency_ms: float
    input_tokens: int
    output_tokens: int
```

No user content, no project paths, no environment data.

## Off-switch

`TELEMETRY=off` (or unset) shuts down every consumer:
- `pyotel_collector.py` refuses to start.
- `ingest.read_jsonl()` returns an empty list.
- `make telemetry-report` prints a "telemetry off" message and exits 0.
- `make atlas` (with TELEMETRY=on at build) needs explicit opt-in; default is off even when telemetry is collected.

The off-switch is checked at every layer to avoid surprise.

## Decay integration

`scripts/decay_check.py` reads recent telemetry to flag skills that have not fired in 60+ days as "decaying via usage" — distinct from time-based decay (which fires on `last_reviewed` age). Usage-decay is informational; it doesn't block `make check`. The point is to surface skills that may be ready for retirement before the maintainer hits the 180-day block band.

## Related

- [`docs/adr/0048-skill-telemetry-privacy.md`](../../docs/adr/0048-skill-telemetry-privacy.md) for the design rationale.
- [`tests/telemetry/`](../../tests/telemetry/) for the boundary contract tests.
- `scripts/skill_identity.py` for the canonical skill-identity helper.
- `otel_collector/README.md` for the docker-compose flavor.
