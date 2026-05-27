---
name: ci-failure-triage
description: Use when a CI pipeline has gone red and the user needs to root-cause and fix the failure across CI, code-quality, lint, typecheck, test, Docker, or PR check stages.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [ci, CI, code-quality, testing, debugging]
scope: [ai-backend, mcp, any]
---

# CI Failure Triage

A short, disciplined loop for CI failures. Do not treat the pasted log as the
whole truth until you identify the failing stage and reproduce the smallest
matching check locally.

## When NOT to use this skill

- The Sonar PR-mode gate specifically failed after a green local pre-push. Use
  `sonar-pr-gate` instead for that precise trap.
- The failure is clearly a VPN connectivity problem. Use `vpn-connectivity-check`
  first.

## Workflow

1. **Capture the failure identity.**
   - Repo, branch, commit SHA, PR, job name, stage name, and exact failed command.
   - If the log is truncated, ask for the missing part only after checking local
     job scripts, Jenkinsfile, Makefile, pyproject.toml, package.json, Dockerfiles,
     and CI config.

2. **Classify the failure.**
   - Dependency/bootstrap: install, lockfile, image, cache, credentials, network.
   - Static quality: lint, format, typecheck, Sonar, coverage, security scan.
   - Test failure: unit, integration, e2e, scenario, flaky or deterministic.
   - Deployment/release: build artifact, migration, registry, environment.

3. **Reproduce locally at the narrowest seam.**
   - Run the exact failed command first if it is safe.
   - If CI runs a wrapper, inspect the wrapper before guessing.
   - For Sonar, separate local code issues from remote quality-gate state.
   - For Docker failures, check the image, compose project, env file, and mounted
     paths before changing application code.

4. **Fix the root cause.**
   - Prefer code, test, config, or lockfile fixes over suppressions.
   - Do not weaken assertions, coverage thresholds, or quality gates unless the
     user explicitly accepts that tradeoff.
   - After fixing, run the relevant linter or formatter on touched files, then the
     same local check that failed in CI.

5. **Close the loop.**
   - Report the failed stage, cause, changed files, and verification command.
   - If the failure is external or flaky, say what evidence supports that and what
     retry or infrastructure action is needed.
   - If recurring, add a prevention step only when it is small and local:
     pre-commit, lint-guard, CI script assertion, dependency pin, or doc note.

## Guardrails

- Keep logs in working notes or final status, not in product docs.
- Never copy tokens, cookies, registry credentials, or secret env values from CI.
- Do not push to main or develop; work on branches or worktrees.
- Before destructive cleanup of CI artifacts, containers, or worktrees, show the
  exact target list and get confirmation.
