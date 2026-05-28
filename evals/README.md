# Evals

LLM-judge eval suites that exercise one playbook skill end-to-end against a held-out case set. Evals run slower than `make check` (they call an LLM) and gate per-skill behavior, not artifact shape. They are a quality harness, not a 9th content type.

## What an eval is

An eval is a small directory containing structured cases and a judge rubric for one skill. The runner (`scripts/eval_runner.py`) walks each case and asserts the skill body satisfies the case's assertions. Today's static mode runs deterministic shape checks against the skill body without calling an LLM; the future dynamic mode will spawn a subagent per case and score the response against `judge.md`. Pass/fail is per-case; aggregate pass rate gates the skill's freshness for production use.

Different from `tests/` (which checks installer behavior, not skill behavior) and from `make check` (which lints artifact shape, not skill quality). Evals answer: "does the SKILL.md still encode the discipline its author intended, including under cosmetic edits that don't change behavior?"

## What ships in this directory

| Eval suite | Skill under test |
|---|---|
| `ci-failure-triage/` | `base/skills/engineering/ci-failure-triage/SKILL.md` |

This is a starter set. More suites land as skills mature and the maintainer authors per-skill `cases.yaml` + `judge.md`. `ls evals/` is the source of truth.

Each subdir has the same shape:

```
evals/<skill-slug>/
├── cases.yaml           # structured assertions against the SKILL.md (deterministic)
├── judge.md             # natural-language rubric describing what good looks like
└── README.md            # (optional) one-paragraph orientation per suite
```

## Schema

### `cases.yaml`

```yaml
# Eval cases for skills/<category>/<skill-slug>/SKILL.md
cases:
  - name: covers when-to-use trigger
    skill: base/skills/engineering/ci-failure-triage/SKILL.md
    assertions:
      - type: section_present
        pattern: when to use

  - name: distinguishes fix vs flake
    skill: base/skills/engineering/ci-failure-triage/SKILL.md
    assertions:
      - type: body_contains
        pattern: (flak|regression|repeat)

  - name: frontmatter complete
    skill: base/skills/engineering/ci-failure-triage/SKILL.md
    assertions:
      - type: frontmatter_has
        key: name
        value: ci-failure-triage
      - type: frontmatter_has
        key: owner
      - type: frontmatter_has
        key: last_reviewed
```

Supported assertion types today:

| `type` | What it asserts | Required keys |
|---|---|---|
| `section_present` | A markdown H2 / H3 section matches the pattern (case-insensitive regex). | `pattern` |
| `body_contains` | The SKILL.md body (everything after the frontmatter) matches the pattern. | `pattern` |
| `frontmatter_has` | The frontmatter contains the named key; if `value` is given, the value matches exactly. | `key`, optional `value` |

Patterns are Python regex. Use parens for alternation: `(flak|regression|repeat)`.

### `judge.md`

Plain markdown. Names the rubric the runner uses for scoring narrative quality on top of the deterministic assertions. Treat it as both a doc for human reviewers and the prompt fragment the dynamic-mode runner will feed to its judge LLM.

Example (`evals/ci-failure-triage/judge.md`):

```markdown
# ci-failure-triage judge

## Scoring rubric (static mode)

Five cases ensure the skill still encodes the fix-vs-flake discipline and concrete escalation surface:

1. **Trigger discipline.** Skill names a when-to-use.
2. **Fix vs flake distinction.** Body references flakiness or regression or repeat-run vocabulary.
3. **Sonar/lint coverage referenced.** Body covers Sonar PR gates or lint guards.
4. **Actionable next step.** Body uses classify / root cause / next step vocabulary.
5. **Frontmatter completeness.**

## Future dynamic mode

Fixture failures to add:
- A Sonar PR-mode coverage drop (should suggest specific test additions)
- A flaky pytest that passes 3/4 (should suggest 20x or 30x re-run before "fix")
- A real regression (should escalate to bisect)
- A lint-only failure (should resolve with --fix not requeue)
```

## How the runner consumes evals

```bash
make eval                                                # run every suite
python3 scripts/eval_runner.py ci-failure-triage         # run one suite (positional)
```

The runner accepts a positional `[suite]` argument; per-case filtering is not yet supported by the CLI. Today's static mode reads `cases.yaml`, walks each assertion against the skill body, and exits non-zero on any failure. The future dynamic mode will additionally feed each case + the skill body to a judge LLM scored against `judge.md` for narrative quality, returning a `[0, 1]` rubric score per case.

## How to add a new eval suite

1. Create `evals/<skill-slug>/` matching the skill's install_name (e.g. `evals/ci-failure-triage/` for `base/skills/engineering/ci-failure-triage/`).
2. Author `cases.yaml` with a happy-path case, an anti-pattern case (something the skill should REFUSE), and one frontmatter-completeness case.
3. Author `judge.md` with concrete rubric items. Vague rubrics produce flaky judges in the dynamic mode.
4. Run `make eval` and confirm the suite passes against the current skill.
5. Open a PR; reviewer checks that the cases match the skill's documented `## When to use` and `## When NOT to use` sections.

## Quality bar

- A suite covers at least 3 cases: happy path, edge case, anti-pattern (something the skill should REFUSE).
- Each `body_contains` pattern is concrete (`(flak|regression|repeat)`), not aspirational (`good practices`).
- A suite that consistently passes for the wrong reason (e.g. the assertion regex is too lenient) should tighten the regex, not loosen the case.
- Suites SHOULD reference the skill's frontmatter `description` so reviewers can spot drift between what the skill promises and what the eval rewards.

## How decay relates to evals

A skill that fails its eval suite is not auto-marked decayed; decay is time-based (60-day notice / 90-day warn / 180-day block per `scripts/decay_check.py`). But a skill the eval flags should refresh `last_reviewed` only AFTER the eval passes again, otherwise the timer is gameable. The CONTRIBUTING.md ships this as a quality bar: refresh `last_reviewed` when the skill is re-verified, not on schedule.

## References

- ADR-0017: eval harness pattern.
- `scripts/eval_runner.py` for the runner implementation.
- `base/skills/README.md` for the skill contract that evals exercise.
- `evals/AGENTS.md` for concise edit rules during in-flight authoring.
