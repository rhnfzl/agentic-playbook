---
name: post-iter-review
description: Use when an iteration loop has just completed successfully and the user wants to run the three-stage pre-push review pipeline (codex:review, adversarial review, review-loop) before pushing.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [review, codex, pre-push, quality-gate, testing]
scope: [ai-backend, mcp, any]
---

# Post-iter Review Pipeline

The per-iteration QA gate: three sequential foreground reviews against `develop`,
each followed by a classify-and-fix pass, then a re-iter to confirm the fixes did
not regress. Iter green is necessary but not sufficient; this pipeline is the
sufficient gate.

## When NOT to use this skill

- There are no changes vs base (`git diff --shortstat <base>...HEAD` is empty).
- The user explicitly wants a single review only (just `/codex:review`).
- The user is mid-iter and has not declared the iter successful.

## Pipeline contract

Five phases, sequential, foreground only. Each phase blocks the next.

```
1. codex:review              (find general correctness issues)
2. classify + fix findings
3. codex:adversarial-review  (challenge design + assumptions)
4. classify + fix findings
5. review-loop:review-loop   (iterative claim-vs-evidence loop)
6. classify + fix findings
7. re-run iter               (verify fixes did not regress)
```

## Step 0: Pre-flight

Read the project's conventions (AGENTS.md, CLAUDE.md, memory) before running any
review. Cache the guardrails list for all subsequent classification phases.

Verify there is something to review:

```bash
git rev-parse --abbrev-ref HEAD
git status --short --untracked-files=all
git diff --shortstat develop...HEAD
```

If the diff is empty AND no untracked files, stop and report "Nothing to review
against develop." Detect the iter command from Makefile targets, then pyproject.toml
/ package.json scripts, then ask once.

## Step 1: codex:review (foreground)

```
/codex:review --wait --base develop
```

Read verbatim Codex output. Do not paraphrase before classifying.

## Step 2: Classify and fix

Three buckets for every finding:

- **Apply (auto-fix):** real bug, missing test for a real branch, security hole,
  contract violation, broken invariant, dead code, type errors, regressions vs
  `develop`.
- **Ignore:** style preferences that conflict with lint config, "would be nice"
  refactors outside change scope, over-defensive checks, single-use abstractions,
  comments explaining what code already says.
- **Defer:** cross-team coordination needed, architectural surface beyond branch
  scope, release-gated decision, or fix exceeding ~150 lines that is not
  same-substrate. Otherwise fold into the current PR.

Apply the Apply bucket without asking. Re-run review until clean or three
consecutive runs surface the same un-fixable finding (escalate to user).

## Step 3: codex:adversarial-review (foreground)

```
/codex:adversarial-review --wait --base develop
```

Adversarial findings question the implementation choice itself. The Apply bucket
is narrower (real assumption violations, real ignored edge cases). The Defer
bucket is wider (architectural pushback that does not block this PR).

## Step 5: review-loop:review-loop (foreground)

Auto-generate a 2-3 sentence validation description from the diff, then invoke:

```
/review-loop:review-loop <generated task description>
```

Template: "Validate and harden the recent changes against develop on branch
`<branch>`. Scope: `<one-line summary>`. Coverage to verify: `<key invariants>`."

## Step 7: Re-run iter

The iter must be green again after review fixes. If it fails: diagnose the
regression, revert the offending fix + reclassify to Defer, or fix the regression
and re-run. Do not push with a red iter.

## Commit discipline

Pre-commit hooks often auto-modify staged files. Verify after every commit:

```bash
BEFORE=$(git rev-parse HEAD)
git commit -m "..."
AFTER=$(git rev-parse HEAD)
[ "$BEFORE" = "$AFTER" ] && { git add -A && git commit -m "..."; }
```

## Argument handling

- `--base <ref>`: defaults to `develop`.
- `--iter-cmd "<cmd>"`: override the auto-detected iter command.
- `--no-iter`: skip step 7.
- `--no-preflight`: skip step 0 guardrails load.
- `--focus "<text>"`: extra adversarial focus text (adversarial review only).

## Output framing

Bracket every run with `=== POST-ITER-REVIEW PIPELINE START ===` and
`=== POST-ITER-REVIEW PIPELINE END ===`. Include per-step finding counts
(applied / deferred / ignored) and the re-iter result.

## Guardrails

- Use Bash synchronously (no `run_in_background: true`) for every step.
- Always pass `--wait` to codex commands.
- Never run `git push` or any remote write. Push is the user's to drive.
- Model and reasoning effort live in `~/.codex/config.toml`; do not pass
  `--model` flags to codex CLI.
