# evals/ci-failure-triage/

LLM-judge eval suite for [`base/skills/engineering/ci-failure-triage/`](../../base/skills/engineering/ci-failure-triage/SKILL.md). Five cases that assert the skill still encodes the fix-vs-flake discipline and a concrete escalation surface.

## What this suite asserts

Each case is one assertion against the SKILL.md body or frontmatter:

| Case | Assertion |
|---|---|
| `covers when-to-use trigger` | The skill has a `## When to use` section. |
| `distinguishes fix vs flake` | Body references flakiness, regression, or repeat-run vocabulary. Single-shot pass on a fresh image is NOT proof of fix; the skill must say so. |
| `sonar or lint coverage referenced` | Body covers Sonar PR gates or lint guards (the team's coverage discipline). |
| `actionable next step shape` | Body uses classify / root-cause / next-step vocabulary so the triage produces a punch list, not vibes. |
| `frontmatter complete` | Frontmatter has `name`, `owner`, `last_reviewed`. |

## How to run

```bash
make eval                                                # all suites
python3 scripts/eval_runner.py --suite ci-failure-triage # this suite only
python3 scripts/eval_runner.py --suite ci-failure-triage --case "frontmatter complete"
```

## Failure modes

If the skill is edited and the eval fails:

1. Read the failing assertion. The `pattern` field in `cases.yaml` shows the regex.
2. Decide: did the SKILL.md drift away from the discipline (fix the SKILL.md) or did the eval pattern get too strict (loosen the regex)?
3. If the former, update the SKILL.md and refresh `last_reviewed`. If the latter, tighten the alternative pattern instead of dropping the case.

## Future dynamic mode

The current eval is static (regex over the SKILL.md). The dynamic mode would also exercise the skill against real CI failure fixtures (a Sonar coverage drop, a flaky pytest, a real regression, a lint-only failure) and judge the agent's response with an LLM. The fixture list lives in [`judge.md`](judge.md).

## Related

- [`base/skills/engineering/ci-failure-triage/SKILL.md`](../../base/skills/engineering/ci-failure-triage/SKILL.md) for the skill under test.
- [`evals/README.md`](../README.md) for the suite schema (`cases.yaml` + `judge.md`).
- [`cases.yaml`](cases.yaml) for the structured assertions.
- [`judge.md`](judge.md) for the natural-language rubric.
