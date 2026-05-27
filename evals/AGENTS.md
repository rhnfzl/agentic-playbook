# Evals

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

LLM-judge eval suites per skill. Each subdirectory tests one skill against a held-out prompt set; the judge model scores the response against a concrete rubric. Different from `tests/` (installer regressions) and `make check` (artifact lint).

## What Lives Here

- `<skill-slug>/` subdirectories, one per skill under eval.
- `<skill-slug>/prompts.yaml` and `<skill-slug>/criteria.yaml` per suite.
- Optional `<skill-slug>/fixtures/` directory for static input data the prompts reference.
- `README.md` enumerates the schema and the quality bar.

## Local Commands

- `make eval` from repo root runs every suite via `scripts/eval_runner.py`.
- `python3 scripts/eval_runner.py --suite <name>` runs one suite.
- `python3 scripts/eval_runner.py --suite <name> --prompt <id>` runs one prompt.

## Edit Rules

- One subdirectory per skill, matching the skill's `install_name`.
- `prompts.yaml` + `criteria.yaml` are required; `fixtures/` is optional.
- Criteria are concrete (verifiable in the response text), not aspirational.
- Every suite has at least 3 prompts: happy path, edge case, anti-pattern.
- No em dashes in prompts, criteria, or README files (the project-wide rule).

## Required Checks

- `make eval` exits 0 (all suites pass).
- Each suite's `criteria.yaml` references the same trigger language as the skill's `## When to use` section.
- Criteria do not test for hallucinations the skill itself does not warn against.

## Required Skills

- `/playbook-promote` to graduate a draft skill once its eval suite passes.
- `/playbook-retrospective` to capture eval failures as new skill iterations.

## Do Not

- Add an eval suite for a skill that does not exist yet. Author the skill first.
- Use the judge model to score "vibes." Concrete criteria only.
- Hardcode model IDs in `criteria.yaml`; the runner picks the active model from `scripts/eval_runner.py`.
- Treat a failing suite as a reason to weaken the rubric. Fix the skill or document why the failure is acceptable.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a suite or tightening a rubric.
