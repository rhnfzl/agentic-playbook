# Evals

Owner: Rehan
last_reviewed: 2026-05-28

## Purpose

Per-skill eval suites that exercise one skill against deterministic assertions today, with an LLM-judge dynamic mode on the roadmap. Each subdirectory tests one skill. Different from `tests/` (installer regressions) and `make check` (artifact lint).

## What Lives Here

- `<skill-slug>/` subdirectories, one per skill under eval.
- `<skill-slug>/cases.yaml` (structured assertions) and `<skill-slug>/judge.md` (natural-language rubric) per suite.
- Optional `<skill-slug>/fixtures/` directory for static input data future dynamic-mode cases will reference.
- `README.md` enumerates the schema and the quality bar.

## Local Commands

- `make eval` from repo root runs every suite via `scripts/eval_runner.py`.
- `python3 scripts/eval_runner.py <suite-name>` runs one suite (positional argument).

## Edit Rules

- One subdirectory per skill, matching the skill's `install_name`.
- `cases.yaml` + `judge.md` are required; `fixtures/` is optional.
- Cases use concrete assertion types (`section_present`, `body_contains`, `frontmatter_has`); patterns are verifiable regex over the SKILL.md body or frontmatter, not aspirational claims.
- Every suite has at least 3 cases: happy path, edge case, anti-pattern.
- No em dashes in cases, judges, or README files (the project-wide rule).

## Required Checks

- `make eval` exits 0 (all suites pass).
- Each suite's `cases.yaml` references assertion patterns that map to the skill's `## When to use` section.
- Cases do not test for hallucinations the skill itself does not warn against.

## Required Skills

- `/playbook-promote` to graduate a draft skill once its eval suite passes.
- `/playbook-retrospective` to capture eval failures as new skill iterations.

## Do Not

- Add an eval suite for a skill that does not exist yet. Author the skill first.
- Use the judge model to score "vibes." Concrete cases only.
- Hardcode model IDs in `judge.md`; the future dynamic-mode runner picks the active model from `scripts/eval_runner.py`.
- Treat a failing suite as a reason to weaken the rubric. Fix the skill or document why the failure is acceptable.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a suite or tightening a rubric.
