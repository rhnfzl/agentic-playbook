# 0045. Cross-adapter trace contract

## Status
Accepted (2026-05-28). Phase 1 shipped the data model and the fixture
replay path. Phase 2B added the live Claude Code provider. Phase 2C
folded both into a single OTel parser so the live and fixture paths
cannot drift on envelope handling, span ordering, or unknown-op
behavior.

## Context

ADR-0044 introduced trajectories as the 8th content type and named
ADR-0045 as the home for the trace contract every adapter trace shim
must satisfy. Without this contract the harness would either:

- Lock into one adapter's native trace format and lose portability
  (the central product claim of the playbook), or
- Accept arbitrary per-adapter shapes and push the normalization cost
  into every consumer (matcher, judge, calibrate, recorder).

The hybrid match contract in ADR-0046 reads only `TraceRecord`. The
DSL matcher and the LLM judge never import a per-adapter module. So
the trace contract is the single seam the cross-adapter promise rests
on.

Two practical pressures shape the shape:

1. **OpenTelemetry's `gen_ai.*` conventions** are the only convergent
   prior art. Claude Code emits them natively. Codex / Cursor /
   Windsurf are either already aligned or close enough to map with a
   per-adapter shim.
2. **Authoring tools need to round-trip.** The recorder
   (`scripts/trajectory_record.py`) writes a fixture that the
   calibrate and verify tools will read back. If the fixture format
   diverges from what the live provider emits, the author thinks
   their trajectory passes when it does not.

## Decision

### Event taxonomy

A trace is an ordered list of `TraceEvent` records plus a `TraceRecord`
envelope. Kinds (`TRACE_EVENT_KINDS` in
`scripts/adapters/trace_record.py`):

| kind             | name field            | arguments        | when emitted                              |
|------------------|-----------------------|------------------|-------------------------------------------|
| `skill_load`     | the skill slug        | None             | `gen_ai.operation.name=skill_load`        |
| `tool_call`      | the tool name         | dict (parsed)    | `gen_ai.operation.name=tool_call`         |
| `tool_result`    | the tool name         | dict (parsed)    | reserved; not yet emitted by any adapter  |
| `model_response` | the model name (`chat`) or span name (unknown ops) | None | `gen_ai.operation.name=chat` OR any unknown op |

`tool_result` is reserved so adapters that distinguish "I asked the
tool" from "I got back" can land them as separate events later
without a kind-set expansion ADR.

### Span attribute mapping

The adapter shim is responsible for reading the native span source and
producing flat span dicts in OpenTelemetry shape:

```json
{
  "name": "Write",
  "startTimeUnixNano": "1717000000000000000",
  "endTimeUnixNano":   "1717000000010000000",
  "attributes": [
    {"key": "gen_ai.operation.name", "value": {"stringValue": "tool_call"}},
    {"key": "tool.name",             "value": {"stringValue": "Write"}},
    {"key": "tool.arguments",        "value": {"stringValue": "{\"path\": \"a.md\"}"}}
  ]
}
```

The shared parser
(`scripts/adapters/claude_code_trace.spans_from_text` +
`_span_to_event`) reads:

- `gen_ai.operation.name` -> kind dispatch
- `gen_ai.request.model` -> `TraceRecord.model`
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` -> token totals
- `tool.name` -> event name (fallback: span name)
- `tool.arguments` -> JSON-decoded into `event.arguments`
- `skill.name` -> event name on skill_load

OTLP envelope nesting (`resourceSpans -> scopeSpans -> spans`) is
flattened transparently. Flat single-span lines and nested envelope
lines may interleave in the same input; the parser handles both.

### Time-ordered sequencing

Spans are sorted by `startTimeUnixNano` BEFORE `seq` numbers are
assigned. Sources that emit on multiple channels (live Claude Code
writes spans to both stdout and stderr depending on Node version) get
the same event order as a fixture replay. The harness assertion
primitives `first_skill_loaded` and `call_order` depend on this; a
seq-by-pipe-order bug in Phase 2B made these assertions flip on
mixed-channel traces, which Phase 2C fixed by routing the live path
through the same parser.

### Unknown operations

Span attributes whose `gen_ai.operation.name` is none of the
recognized values are preserved as `kind=model_response` with
`raw_attrs` filled. The matcher does not gate on these but a human
inspecting the trace can still see them. Two reasons:

1. The OTel `gen_ai.*` set is evolving; refusing to ingest an unknown
   op would make every operational rev break the harness.
2. The Phase 2B provider used to silently drop unknown ops. The
   unified parser keeps them. Both behaviors are defensible; the
   ADR records the choice so future drift is a deliberate ADR
   amendment, not an accident.

### Adapter registry

`KNOWN_TRACE_ADAPTERS` (frozenset in `trace_record.py`) is the single
source of truth for what `adapter_scope` may name. Adding a new
adapter requires:

1. A new entry in `KNOWN_TRACE_ADAPTERS`.
2. A shim under `scripts/adapters/<adapter>_trace.py` that produces
   spans satisfying the contract above.
3. An update to ADR-0044's `Reject if` cost mathematics so the
   cross-adapter share considers the new adapter.

Triplicate registries in the harness, the linter, and the matcher
were collapsed in a Phase 2A review round; never reintroduce them.

## Reject if

- Two consecutive Tier-1 adapters' shims grow more than 50 lines of
  per-adapter mapping code. That is the signal that the gen_ai
  contract is no longer a shared vocabulary and either the contract
  needs a layer above OpenTelemetry or the adapter does not really
  fit the cross-adapter promise.
- Round-trip parity between the live `claude` provider and the
  fixture replay breaks in CI more than twice in a quarter. The
  hardening goal of Phase 2C was "one parser, one contract"; reverts
  to dual-parser behavior must come with an ADR amendment, not a
  silent shim divergence.

## Consequences

- `scripts/adapters/trace_record.py` owns the `TraceEvent` /
  `TraceRecord` NamedTuples and the `KNOWN_TRACE_ADAPTERS` registry.
  Adding a kind is an amendment to this ADR.
- The fixture replay (`parse_otel_jsonl`) and the live provider
  (`ClaudeCodeProvider`) share `claude_code_trace.events_from_text`.
  Provider-specific concerns (workdir artifact hashing, env
  allowlist, subprocess timeout) stay in the provider.
- Recorder fixtures (`save_fixture` in `trajectory_record.py`) are
  written in the same flat span shape the live provider emits, so a
  recorded fixture can be replayed by `parse_otel_jsonl` without a
  separate "recorder fixture" parser path.

## Source

- OpenTelemetry. Semantic conventions for generative AI.
  https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Anthropic. Claude Code monitoring and usage.
  https://docs.claude.com/en/docs/claude-code/monitoring-usage
- ADR-0044 (trajectory content type) for the upstream contract.
- ADR-0046 (DSL + hybrid match) for the consumer of this trace data.
