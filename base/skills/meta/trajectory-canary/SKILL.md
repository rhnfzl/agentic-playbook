---
name: trajectory-canary
description: Use as the smoke-test skill for the cross-adapter trajectory harness. Lightweight, no-op skill that exists only so the harness can run an end-to-end trajectory against a known target. Do NOT invoke as a real workflow.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-28
tags: [meta, testing]
scope: [any]
---

# Trajectory Canary

A canonical skill used by the cross-adapter trajectory harness (ADR-0044,
ADR-0045) as its end-to-end smoke target. The harness has its own self-tests
covering the matcher, the trace adapters, and the schema; this skill exists
so a real LLM run can be exercised against a frozen target without depending
on production skills (which evolve and would invalidate the smoke fixture).

## Behavior

When invoked, the agent should:

1. Read this file once.
2. Write a single artifact at `./trajectory-canary-output.md` containing
   the literal text "canary chirped".
3. Stop.

That's it. The trajectory at `base/trajectories/trajectory-canary/canary.yaml`
asserts that the artifact was written and contains the expected text.

## When NOT to use this skill

- Any real workflow. This skill is intentionally trivial.
- As a template for new skills. See `base/skills/meta/write-a-skill/` for that.
