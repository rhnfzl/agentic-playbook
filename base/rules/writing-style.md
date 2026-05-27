# Writing Style

Lead with plain-language product context before technical details in ALL documents, comments, PR descriptions, Slack messages, and HTML artifacts.

## The shape

1. **What it does for the user** (one sentence, no jargon)
2. **Why it matters** (one sentence, business impact or constraint)
3. **How it works technically** (the implementation details)

## Example

Bad:

```
This refactor migrates the geocoder dependency from city-level to district-level
resolution to handle ambiguous user input.
```

Good:

```
When a recruiter types "amsterdam" in the city filter, the platform should match
candidates in any Amsterdam district, not just the central city. This refactor
migrates the geocoder from city-level to district-level resolution.
```

## Why this matters

Engineers, PMs, and stakeholders all read the same artifacts. Plain-language framing reaches everyone; technical-first framing alienates non-engineers and slows down PM review. The technical detail still goes in. It just isn't the opening sentence.

## Application

Use this shape in:

- PR descriptions
- Commit messages (commit summary is plain-language; body is technical)
- Jira tickets
- HTML decision aids and plans
- Slack updates
- Code comments that explain WHY (not WHAT)
