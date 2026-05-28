# 0046. Trajectory DSL surface + hybrid DSL/LLM-judge match semantics

## Status
Accepted (2026-05-28). Phase 1 shipped the DSL half. Phase 2 added the
LLM-judge half via `scripts/trajectory_judge.py` and the live
`anthropic_judge_client.HttpAnthropicJudgeClient`, plus the
`JudgeClient` Protocol seam for fakes in tests. The hybrid contract is
now fully implemented end to end.

## Context

ADR-0044 introduced the trajectory content type and named ADR-0046 as the
home for two coupled decisions:

1. The shape of the trajectory DSL, i.e. which assertion primitives the
   matcher understands and how they compose.
2. The hybrid match contract: DSL assertions evaluate first (cheap,
   deterministic); if they pass, the LLM-judge runs against the
   `llm_judge.rubric` and threshold (slower, costs money).

The two are coupled because the linter, reader, and matcher must all
agree on which DSL keys are valid and where the cutover from "I can
machine-check this" to "I need an LLM" sits.

## Decision

The DSL surface (subject to extension via ADR amendment; new
primitives ship in `scripts/trajectory_matcher.py` and get a matching
entry in `_PRIMITIVES`):

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

Glob semantics are POSIX-ish but path-aware: a pattern WITHOUT a
`/` matches only basenames, so `final_artifact_path: "*.md"` does not
match `subdir/foo.md`. Use `**/*.md` for "any markdown file at any
depth." The check lives in
`scripts/trajectory_matcher._path_aware_glob_match`.

Hybrid match contract (fully shipped):

1. The matcher runs the DSL assertions. If any fail, the trajectory
   fails without invoking the LLM judge (cost: $0).
2. If DSL passes AND a judge_client is wired AND the trajectory has
   an `llm_judge` block, the LLM judge evaluates the trace against
   `llm_judge.rubric` and produces a score in `[0, 1]`.
3. The trajectory passes overall iff DSL passed AND judge score >=
   `llm_judge.threshold`.
4. Per phrasing, per adapter, per scenario. The matrix aggregates
   upward per ADR-0044.

Budget interactions (Phase 2C, review-fold):

- `max_provider_calls` caps the TOTAL number of trace_provider
  spawns (initial + retries). The retry loop refuses additional
  attempts once the budget is exhausted.
- `max_judge_calls` caps LLM-judge invocations independently. When
  the budget is exhausted and a trajectory has `llm_judge` configured,
  the cell FAILS (review-fold P2: the contract is "DSL pass AND judge
  pass"; an unavailable judge cannot satisfy it).
- `judge_infra_fail` distinguishes a 429 / parse / refusal from a
  quality miss so operators can route the failure correctly.
- `--strict` refuses to start a run when any candidate trajectory
  has `llm_judge` configured but no judge_client is wired, removing
  the silent DSL-only-pass mode.

Judge implementation: `scripts/trajectory_judge.py` holds the
`JudgeClient` Protocol and `evaluate_judge`. The default live client
is `HttpAnthropicJudgeClient` in `anthropic_judge_client.py`, which
uses stdlib `urllib` for the Anthropic Messages API (no SDK
dependency). Tests inject a stub via the Protocol.

## Reject if

- A DSL primitive's semantic surprises authors more than once. Codex
  review-round-3 already caught `call_order` first-occurrence-only
  semantics that the docstring did not advertise; that name was kept,
  but if more semantics drift surfaces, prefer renaming over redefining.
- LLM-judge calibration score range above 0.1 across N temperature-0
  runs (per ADR-0044 reject-if). Measured by
  `scripts/trajectory_calibrate.py` as `max(scores) - min(scores)`
  across successful runs (infra errors are excluded so a single 429
  cannot tag a stable rubric as noisy). At that noise floor the
  hybrid contract degrades to "DSL only" because the judge half adds
  variance without signal.

## Consequences

- `scripts/trajectory_matcher.py` is the canonical implementation of the
  DSL primitives table. Adding a primitive requires: (a) a new
  `_check_<name>` function, (b) registration in `_PRIMITIVES`, (c) lint
  coverage if the value shape is structured, (d) an amendment to this
  ADR documenting the new primitive's semantics.
- Cost mathematics from ADR-0044's reject-if (claude-only share, etc.)
  now include LLM-judge cost. `max_judge_calls` is the operator's lever
  to bound that spend; a budget-exhausted judge fails the cell so the
  matrix output reflects the actual contract status.

## Source

- ADR-0044 (trajectory as 8th content type) for the upstream contract.
- ADR-0045 (cross-adapter trace contract) for the data shape this
  matcher consumes.
- DevAI / Agent-as-a-Judge (Zhuge et al. 2025) for the hybrid-match
  pattern: deterministic gates first, LLM judge second.
- LangChain agentevals `trajectory_match` and `trajectory_llm_match`
  for the API precedent.
