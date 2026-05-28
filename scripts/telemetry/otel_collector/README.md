# OTLP collector for the playbook telemetry layer

Two options to run the collector. Both write to
`~/.coding-agents-playbook/telemetry/skills.jsonl`.

## Option A: docker-compose (industry standard)

```bash
make telemetry-init   # docker compose up -d
make telemetry-stop   # docker compose down
```

Uses `otel/opentelemetry-collector-contrib`. Listens on
`localhost:4317` (gRPC) and `localhost:4318` (HTTP). Strips prompt
and response bodies in the processor pipeline before write.

Requires docker. If docker is not installed, use Option B.

## Option B: pure-Python (no docker)

```bash
python3 scripts/telemetry/pyotel_collector.py
# Ctrl-C to stop
```

Stdlib-only OTLP/HTTP receiver on `localhost:4318`. No protobuf
parsing: configure your client to emit JSON via
`OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json`.

## Configuring Claude Code to emit telemetry

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json  # only for Option B
claude  # normal usage; spans flow to the collector
```

Claude Code's `gen_ai.*` emission is documented at
https://code.claude.com/docs/en/monitoring-usage. The collector
drops prompt/response bodies on write; you can verify this by
running `head -1 ~/.coding-agents-playbook/telemetry/skills.jsonl`
after a session and confirming no prompt content.

## Disabling telemetry entirely

Set any of these env vars to a falsy value (`off`, `0`, `false`, `no`,
`disabled`):

- `TELEMETRY`
- `TELEMETRY_ENABLED`
- `PLAYBOOK_TELEMETRY`

When disabled, `make telemetry-init`, `make telemetry-report`, the
report CLI, and the decay-by-usage check all degrade cleanly.
