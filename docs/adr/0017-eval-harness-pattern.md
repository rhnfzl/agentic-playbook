# 0017. Eval harness pattern for high-risk skills

## Status

Accepted (2026-05-25)

## Context

Some skills carry outsized impact when they misfire (code-review, chat-transcript-debug, mcp-first-boundary-check, ci-failure-triage). Drift in these skills produces drift in code review, debugging, and CI triage across the whole team. v0.2.1 had no harness measuring whether a skill behaves as intended.

## Decision

`scripts/eval_runner.py` provides a two-mode harness:

### v0.3 mode: static assertions

Each high-risk skill gets a directory `evals/<skill>/` with:

- `cases.yaml`: list of cases, each with `name`, `skill` (path to SKILL.md), `assertions` (list of small deterministic checks against body / frontmatter / references)
- `judge.md`: human-readable scoring rubric documenting what the assertions mean and what future dynamic cases will cover

Assertion types: `section_present`, `section_absent`, `body_contains`, `body_absent`, `frontmatter_has`, `reference_exists`.

Runs without LLM API access. Catches skill body drift (missing sections, removed enforcement language, broken references).

### v0.4+ mode: dynamic evaluation

Each suite's `judge.md` lists fixture inputs to add. The harness will spawn a subagent with each case input, capture output, and apply the judge rubric for pass/fail. Requires API access and fixtures.

Each suite owns its fixtures (`evals/<skill>/fixtures/`); the harness does not assume a global fixture format.

## v0.3 coverage

Four reference suites authored:
- `evals/code-review/` (4 cases)
- `evals/chat-transcript-debug/` (4 cases)
- `evals/mcp-first-boundary-check/` (5 cases)
- `evals/ci-failure-triage/` (5 cases)

18 cases total. All pass against current skill bodies.

## Consequences

- Adding a new high-risk skill = adding an eval suite (cases.yaml + judge.md).
- Skill body changes that remove required sections or enforcement language fail the suite at PR time.
- Pass/fail scoring (per locked decision: no Likert) keeps the rubric unambiguous.
- v0.4+ work: build the fixtures and judge invocation flow.

## Related

- v0.3 plan: scope row 8
- agentskills.io guidance: evaluation before broad rollout
