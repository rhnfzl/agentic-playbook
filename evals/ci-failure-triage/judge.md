# ci-failure-triage judge

## Scoring rubric (v0.3 static mode)

Five cases ensure the skill still encodes the fix-vs-flake discipline and concrete escalation surface:

1. **Trigger discipline.** Skill names a when-to-use.

2. **Fix vs flake distinction.** Body references flakiness or regression or repeat-run vocabulary. Single-shot pass on fresh image is NOT proof of fix (per `feedback_flakiness_check_before_cnr` memory).

3. **Sonar/lint coverage referenced.** Body covers Sonar PR gates or lint guards.

4. **Actionable next step.** Body uses classify / root cause / next step vocabulary so the triage produces a punch list, not vibes.

5. **Frontmatter completeness.**

## Future v0.4 dynamic mode

Fixture failures to add:
- A Sonar PR-mode coverage drop (should suggest specific test additions)
- A flaky pytest that passes 3/4 (should suggest 20x or 30x re-run before "fix")
- A real regression (should escalate to bisect)
- A lint-only failure (should resolve with `--fix` not requeue)
