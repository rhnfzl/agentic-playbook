# Evals

LLM-judge eval suites that exercise one playbook skill end-to-end against a held-out prompt set. The 7th content type the playbook ships (after skills, rules, hooks, MCP configs, subagents, commands, prompts), but with a distinct lifecycle: evals run slower than `make check` and gate skill quality, not artifact shape.

## What an eval is

An eval is a small directory containing input prompts and judge criteria for one skill. The runner (`scripts/eval_runner.py`) feeds each prompt to an LLM acting as the skill, then asks a second LLM (the judge) to score the response against the criteria. Pass/fail is per-prompt; aggregate pass rate gates the skill's freshness for production use.

Different from `tests/` (which checks installer behavior, not skill behavior) and from `make check` (which lints artifact shape, not skill quality). Evals answer: "does this skill, when followed by an agent, actually produce the outcome we wanted?"

## What ships in this directory

| Eval suite | Skill under test |
|---|---|
| `code-review/` | `base/skills/engineering/code-review` |
| `chat-transcript-debug/` | `skills/engineering/chat-transcript-debug` |
| `ci-failure-triage/` | `skills/engineering/ci-failure-triage` |
| `mcp-first-boundary-check/` | `skills/engineering/mcp-first-boundary-check` |

Each subdir has the same shape:

```
evals/<skill-slug>/
├── prompts.yaml          input prompts the runner feeds to the skill-acting LLM
├── criteria.yaml         judge rubric (per-prompt pass/fail conditions)
└── README.md             one-paragraph orientation: what scenarios the suite covers
```

The exact list of suites ships in this directory; `ls evals/` is the source of truth.

## Schema

`prompts.yaml`:

```yaml
prompts:
  - id: pr-review-happy-path
    user_message: |
      Review this PR: https://<vcs-host>:<team>/foo/pull-requests/123
    context:
      diff_file: fixtures/pr-123.diff
  - id: pr-review-empty-diff
    user_message: |
      Review this PR with no code changes (docs only)
```

`criteria.yaml`:

```yaml
prompts:
  - id: pr-review-happy-path
    must:
      - "Identifies at least one comment per changed file"
      - "Calls out the code-review convention violations"
      - "Does NOT use `gh` CLI (rule: vcs-not-github)"
    must_not:
      - "Hallucinates a file that isn't in the diff"
```

## How the runner consumes evals

```bash
make eval                                # run every suite
python3 scripts/eval_runner.py --suite code-review
python3 scripts/eval_runner.py --suite code-review --prompt pr-review-happy-path
```

The runner reads LLM-router config from the env, loads the skill from `~/.agents/skills/<slug>/SKILL.md`, runs each prompt through the configured model, then sends each (prompt, response, criteria) tuple to the judge model. Exit code is non-zero when any prompt's `must` condition fails or any `must_not` condition triggers.

## How to add a new eval suite

1. Create `evals/<skill-slug>/` matching the skill's install_name.
2. Author `prompts.yaml` with at least one happy-path prompt + one anti-pattern prompt.
3. Author `criteria.yaml` with concrete `must` / `must_not` conditions; vague rubrics produce flaky judges.
4. Run `make eval` and confirm the suite passes on the current skill.
5. Open a PR; reviewer checks that the criteria match the skill's documented `## When to use` and `## When NOT to use` sections.

## Quality bar

- A suite has at least 3 prompts: happy path, edge case, anti-pattern (something the skill should REFUSE).
- Criteria are concrete, not aspirational. "Names the file" is verifiable; "writes a great review" is not.
- A suite that consistently passes for the wrong reason (e.g. the judge is lenient) should tighten its `must_not` conditions, not loosen the prompt.
- Suites SHOULD reference the skill's frontmatter `description` so reviewers can spot drift between what the skill promises and what the eval rewards.

## References

- ADR-0017 (eval harness pattern).
- `scripts/eval_runner.py` (the runner).
- `skills/README.md` (the skill contract evals exercise).
- `evals/AGENTS.md` (concise edit rules for in-flight authoring).
