# productivity/

General workflow tools: slide decks, meeting briefs, stakeholder communication, handoffs, slack drafts, structured interviews. Skills here help the coding agent do the work around the work, the stuff that surrounds and supports engineering output but isn't code itself.

## What ships here

| Skill | What it does |
|---|---|
| `ask-colleague/` | Consult one distilled colleague persona for a quick read on a question. |
| `ask-team/` | Convene a panel of colleague personas to deliberate on a complex decision. |
| `caveman/` | Compress writing to a terse, blunt register when an audience wants speed over warmth. |
| `distill-slack-persona/` | Build or refresh a colleague's persona file from their Slack history. |
| `frontend-slides/` | Generate an animation-rich HTML presentation with visual style previews. |
| `grill-me/` | Interactive interview-style review: one question at a time on the non-obvious decisions. |
| `grill-with-docs/` | Variant of grill-me that hangs the interview off a canonical doc set (CONTEXT.md glossary, ADRs). |
| `handoff/` | Write a durable handoff doc to `~/Documents/handoffs/` so the next agent can pick up cold. |
| `promote-ticket/` | Promote a draft to a properly-shaped ticket in the team's issue tracker. |
| `spreadsheet/` | Read, transform, and write spreadsheet data (CSV, Excel) with deterministic formulas, not vibes. |

## Schema and authoring

Per `base/skills/README.md`. Productivity skills tend to have rich "When NOT to use" sections because the workflows look similar at first glance: handoff vs human-html artifact, ask-colleague vs ask-team, grill-me vs grill-with-docs.

## When to add a productivity skill

- The workflow involves output for humans (presentation, briefing, ticket, message, handoff).
- The workflow has a deterministic shape (sections, sequence, output medium).
- The workflow benefits from being a reusable affordance rather than a one-off prompt.

For engineering workflows that produce code, use the engineering/ category. For research workflows that produce evidence, use research/.

## Related

- `base/skills/README.md` for the skill format and category contract.
- `base/prompts/README.md` for one-shot prompts that don't yet warrant skill packaging.
- `base/commands/README.md` for user-triggered slash commands (often thin wrappers around productivity skills).
