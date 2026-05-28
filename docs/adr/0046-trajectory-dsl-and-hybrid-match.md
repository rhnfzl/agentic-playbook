# 0046. Trajectory DSL surface + hybrid DSL/LLM-judge match semantics

## Status
Proposed (2026-05-28) — Phase 1 ships only the DSL half; the LLM-judge
half lands with the Phase 2 live trace_provider work.

## Context

ADR-0044 introduced the trajectory content type and named ADR-0046 as the
home for two coupled decisions:

1. The shape of the trajectory DSL — which assertion primitives the
   matcher understands and how they compose.
2. The hybrid match contract — DSL assertions evaluate first (cheap,
   deterministic); if they pass, the LLM-judge runs against the
   `llm_judge.rubric` and threshold (slower, costs money).

The two are coupled because the linter, reader, and matcher must all
agree on which DSL keys are valid and where the cutover from "I can
machine-check this" to "I need an LLM" sits.

## Decision (Phase 1 scope)

The DSL surface as of Phase 1 (subject to extension via ADR amendment;
new primitives ship in `scripts/trajectory_matcher.py` and get a
matching entry in `_PRIMITIVES`):

| Primitive | Value shape | Semantics |
|---|---|---|
| `first_skill_loaded` | str | The first `skill_load` event's name must match. |
| `must_invoke_tool` | str | At least one `tool_call` event with this name. |
| `must_not_invoke_tool` | str | Zero `tool_call` events with this name. |
| `final_artifact_path` | str (glob) | The LAST Write/Edit/NotebookEdit's path must match the glob. Path-aware: `*.md` matches root-level only; `subdir/*.md` and `**/*.md` for nested. |
| `max_total_tool_calls` | int | Bound the trace size. |
| `min_total_tool_calls` | int | Bound the trace size. |
| `call_order` | list[{tool, before}] | Each entry asserts tool X's FIRST occurrence precedes tool Y's FIRST occurrence. Inline list-of-dicts only; block-style YAML rejected by the linter. |
| `no_skill_load_after` | list[str] | Skill loads after the assertion's start must all be in the allowed list. |

Hybrid match contract:

1. The matcher runs the DSL assertions. If any fail, the trajectory fails
   without invoking the LLM judge (cost: $0).
2. Only if DSL passes, the LLM judge evaluates the trace against
   `llm_judge.rubric` and produces a score in `[0, 1]`.
3. The trajectory passes overall iff DSL passed AND judge score >=
   `llm_judge.threshold`.
4. Per phrasing, per adapter, per scenario. The matrix aggregates upward
   per ADR-0044.

Phase 1 ships only step 1 of the contract; steps 2-4 land with the live
trace_provider in Phase 2 (separate ADR-0045 for the trace contract).

## Reject if

- A DSL primitive's semantic surprises authors more than once. Codex
  review-round-3 already caught `call_order` first-occurrence-only
  semantics that the docstring did not advertise; that name was kept,
  but if more semantics drift surfaces, prefer renaming over redefining.
- LLM-judge calibration noise above 0.1 between consecutive runs at
  temperature 0 (per ADR-0044 reject-if). At that noise floor the hybrid
  contract degrades to "DSL only" because the judge half adds variance
  without signal.

## Consequences

- `scripts/trajectory_matcher.py` is the canonical implementation of the
  DSL primitives table. Adding a primitive requires: (a) a new
  `_check_<name>` function, (b) registration in `_PRIMITIVES`, (c) lint
  coverage if the value shape is structured, (d) an amendment to this
  ADR documenting the new primitive's semantics.
- Cost mathematics from ADR-0044's reject-if (claude-only share, etc.)
  ignore LLM-judge cost in Phase 1 because no judge runs. Phase 2 will
  amend the cost envelope.

## Source

- ADR-0044 (trajectory as 8th content type) for the upstream contract.
- ADR-0045 (cross-adapter trace contract; Phase 2 work) for the data
  shape this matcher consumes.
- DevAI / Agent-as-a-Judge (Zhuge et al. 2025) for the hybrid-match
  pattern: deterministic gates first, LLM judge second.
- LangChain agentevals `trajectory_match` and `trajectory_llm_match`
  for the API precedent.
