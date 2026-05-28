# engineering/

Code-focused workflows: code review, CI debugging, refactor patterns, performance investigations, prototyping, test-driven development. Skills here help the coding agent do the day-to-day work of a backend or full-stack engineer.

## What ships here

| Skill | What it does |
|---|---|
| `ci-failure-triage/` | Classify a red CI run into flake vs regression vs new failure; produce a punch list of next steps. |
| `code-review-graph-first/` | Review a PR by walking the code-review-graph MCP first, then the diff. |
| `diagnose/` | Root-cause an issue by walking the request chain (FE → backend → MCP → external API). |
| `improve-codebase-architecture/` | Audit a codebase against architectural smells (god classes, circular deps, hidden coupling) and propose targeted refactors. |
| `lint-guard/` | Run the project's linter on changed files and the full project before commit; auto-fix what's fixable. |
| `post-iter-review/` | After an iteration of edits, run a structured review pass for silent failures, missing tests, and drift. |
| `prototype/` | Spike a new feature in a constrained sandbox; produce a working demo + a rollback plan. |
| `supacode-cli/` | Project-specific CLI workflows for the supacode codebase. |
| `tdd/` | Test-driven development discipline: failing test → minimal implementation → refactor. |
| `to-issues/` | Convert a session's findings into well-structured Jira / Linear / GitHub issues. |
| `to-prd/` | Convert a session's findings into a structured PRD or design doc. |
| `triage/` | Triage a bug report into reproduction + root cause + fix vs workaround decision. |

## Schema and authoring

Per `base/skills/README.md`. Engineering skills tend to ship with concrete worked examples (fixture failures, sample diffs) since the discipline is hard to convey abstractly.

## When to add an engineering skill

- The workflow involves code (reading, writing, reviewing, debugging).
- The workflow is reusable across at least three different projects.
- The workflow has deterministic steps (not just "use good judgement").

For PM, design, or research workflows, use the corresponding category instead.

## Related

- `base/skills/README.md` for the skill format and category contract.
- `base/skills/meta/README.md` for skills about skills (write-a-skill, audits).
- `evals/ci-failure-triage/` as the worked example of an evaluated engineering skill.
