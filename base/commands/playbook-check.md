---
name: playbook-check
description: Run all playbook validation gates (frontmatter, decay, em-dashes, adapter tests) and explain any failures with concrete fix suggestions.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [validation, lint, gates, ci, playbook]
---

# Run the playbook validation gates and explain failures

When the user wants to validate the playbook content before opening a PR (or to investigate a failing gate), this command runs every gate and then translates each failure category into the concrete edit that fixes it.

## When to use

- The user typed `/playbook-check` before pushing a feature branch.
- A teammate's PR is failing one of the CI gates and the user wants to reproduce locally.
- The user just authored or promoted a skill and wants to confirm it lints clean.
- The user is about to do a quarterly audit and wants the current health snapshot.

## When NOT to use

- The user wants to install (use `make install` or `/playbook-doctor`).
- The user wants to author a new skill (use `/playbook-new-skill`).
- The user only wants to know detection state (use `/playbook-doctor`).

## Your job

You run `make check` and `make test`, parse each gate's output, and for any failure you identify the rule that was broken, the file path, and the concrete fix.

## Workflow

1. **Run the validation gates.** From the playbook root:
   ```bash
   make check
   ```
   This runs three gates in order:
   - `scripts/frontmatter_lint.py`: every `skills/*/*/SKILL.md` must have name, description, version, owner, last_reviewed.
   - `scripts/decay_check.py`: warns at 90 days since `last_reviewed`, blocks at 180 days.
   - `scripts/check_em_dashes.py`: no em-dashes or en-dashes in authored prose (top-level docs, rules, ADRs, prompts, skill bodies, scripts, hooks, agents, commands, profiles). The full character list is in `rules/no-em-dashes.md`.

2. **Run the adapter tests.** From the playbook root:
   ```bash
   make test
   ```
   This runs `scripts/test_adapters.py`, which exercises adapter idempotency, target safety, and content preservation across Tier 1 and Tier 2 adapters.

3. **Parse failures by category.** For each failure, identify which gate caught it and report:

   **Frontmatter lint failures**
   - "missing or malformed frontmatter": the file does not start with `---` or has no closing `---`. Add the frontmatter block.
   - "missing or empty field 'X'": add the missing field. Required fields are name, description, version, owner, last_reviewed. Reference an alias from OWNERS.md for the owner field.

   **Decay check failures**
   - 90-day warning: bump `last_reviewed` after reviewing the skill is still accurate.
   - 180-day block: the skill is stale. Review it, update `last_reviewed`, optionally bump `version`. If the skill is no longer relevant, remove it.

   **Em-dash failures**
   - Replace the offending dash with a comma for parenthetical asides.
   - Replace with parentheses for inline clarifications.
   - Replace with a period and a new sentence for harder breaks.
   - The same fixes apply to en-dashes. Both characters are banned per `rules/no-em-dashes.md`.

   **Adapter test failures**
   - Idempotency failure: an adapter wrote different content on a second run with the same inputs. Check the adapter for non-deterministic behavior (timestamps, random ordering, env-dependent paths).
   - Target safety failure: an adapter wrote outside the intended target. Check `resolve_target` usage in the adapter.
   - Content preservation failure: an adapter overwrote a user file without preserving the managed-block markers. Check `upsert_managed_block` usage.

4. **Surface fixes** to the user one category at a time. Group by file. Show the offending line and the exact replacement. Where multiple files share the same issue (e.g., five files with em-dashes), suggest a single fix pass.

5. **Re-run after fixes.** Once the user applies the fixes, re-run `make check` and `make test`. Confirm both exit zero before suggesting commit and push.

## Output

The user sees, per gate:

- The gate name (frontmatter, decay, em-dash, adapter test).
- Pass or fail with the count.
- For each failure: the file path, the offending line or field, and the concrete fix.
- A re-run command if fixes were applied.
- A final summary line: "all gates green" or "N failures remain".

## Reference

The gate scripts live under `scripts/`: `frontmatter_lint.py`, `decay_check.py`, `check_em_dashes.py`, `test_adapters.py`. The em-dash rule body is at `rules/no-em-dashes.md`. Decay thresholds are tuned in `decay_check.py`. The adapter test surface is in `scripts/test_adapters.py`.
