# VCS-pr-review judge

This document describes how the eval suite scores the skill. The harness applies the assertions in `cases.yaml`. The rubric below documents the intent so a human can re-derive each case.

## Scoring rubric (v0.3 static mode)

Each case is pass/fail. The four cases together establish that:

1. **Trigger discipline.** The skill names both when-to-use and when-not-to-use. Skills without anti-triggers misfire on adjacent intents.

2. **Em-dash enforcement.** The skill body references the em-dash rule. PR review is where this gets enforced for the team, so the skill must surface it.

3. **VCS API discipline.** The skill references VCS explicitly and does not fall back to `gh pr ...` commands (per `rules/VCS-not-github.md`).

4. **Frontmatter completeness.** name, owner, last_reviewed all populated and name matches `VCS-pr-review`.

## Future v0.4 dynamic mode

When dynamic eval lands, additional cases will run the skill against fixture PRs:
- A PR with em-dashes in description (should be flagged)
- A PR with hardcoded ticket IDs in code comments (should be flagged)
- A PR that proper handles backwards-compatibility (should NOT be flagged)
- A PR with passing CI but failing local check (should surface the gap)
