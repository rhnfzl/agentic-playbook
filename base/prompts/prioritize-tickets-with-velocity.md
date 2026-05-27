# Prompt: Prioritize tickets with velocity-grounded estimates

Paste the prompt below when you have a backlog of tickets / work items and need an HTML artifact that shows dependencies, parallelism, and estimated effort, grounded in your team's MEASURED velocity rather than gut-feel estimates. Designed for stakeholders (PMs, leads) who need to make sequencing decisions without reading the code themselves.

---

## Canonical template

```
I need to reprioritize these tickets / work items based on what we've discussed so far (meetings + items I provided + any context already in the workspace).

Make me an HTML file using the /human-html skill (or write to docs/human-html/ following YYYY-MM-DD-kind-slug.html naming) showing:

- Each {{PRIMARY_TICKET_FAMILY}} (e.g., R8 tickets, project epics, Jira parent stories) and its dependency / flow relationships
- Which {{SECONDARY_TICKET_FAMILY}} (e.g., MATCH tickets, downstream child stories, cross-team dependencies) connect to each primary
- Which items should go FIRST, which come LATER, which can run in PARALLEL
- Your best-guess ordering, based on the codebase + the context above (state your reasoning briefly per item)
- Estimated days of work per item, based on measured velocity between {{DATE_RANGE_START}} and {{DATE_RANGE_END}} during {{WORK_HOURS}} (e.g., "8:30 AM to 5:00 PM business days")

Pull velocity from {{VELOCITY_SOURCE}} (e.g., VCS commits, Jira ticket close dates, GitHub PR merge timestamps) over the specified date range and compute average days per ticket of comparable complexity.

If you have questions about scope, ticket family, or what counts as "comparable complexity," ask via the AskUserQuestion tool with /grill-me discipline BEFORE making the artifact. Provide detailed multiple-choice options so I can answer quickly.

Render the output as a visual flow (Mermaid is fine) plus a sortable table with: ticket id, title, estimated days, dependency-of, can-parallel-with, recommended phase (now / next / later).
```

## When to use this prompt

- Quarterly / sprint planning when the backlog is too noisy for gut-feel ordering.
- Before a stakeholder meeting where you need to explain WHY a given sequence is recommended.
- After a velocity-measurement window closes; turn the raw numbers into actionable sequencing.
- When two ticket families intersect (e.g., a backend epic + the frontend epic that consumes it) and you need a single picture.
- Before committing to a deadline; calibrate the ask against measured throughput.

## What this prompt is NOT

- Not a substitute for actual planning conversations with the team. The HTML is a decision aid for stakeholders, not a unilateral plan.
- Not for trivial backlogs (under ~5 items). For small lists, a Slack message ordered list is enough.
- Not a Gantt-chart generator. Mermaid flow + table is the right granularity; full Gantt is project-management theater.
- Not for forecasting completion dates. Velocity-based estimates are CALIBRATION, not commitment.

## Why velocity, not gut-feel

Estimates that ignore measured throughput consistently underestimate:
- New types of work the team hasn't done before.
- Items with hidden cross-team dependencies.
- Items that look small but require context-rebuilding (returning to a stale codebase).

Velocity-grounded estimates work because they fold in the friction you actually experience (meetings, code reviews, debugging time, context switches) rather than the "if everything goes well" duration. The DATE_RANGE_START / DATE_RANGE_END parameters force you to specify a recent, representative window rather than an averaged-over-history fantasy.

## Why business hours, not calendar days

A "5-day ticket" estimated against calendar days assumes 24/7 work. Against business hours, the same ticket is more like 9 calendar days (after weekends + meetings + interruptions). Specifying WORK_HOURS makes the estimate honest about what fits in a real workweek.

## Composition with other prompts

- Run `discover-repeatable-workflows.md` first if you notice many tickets look similar; a skill might collapse several into a single workflow.
- Use this prompt's output as input to `clarify-then-deliver.md` when you need to commit to a phase: feed the recommended-now list into the next planning session.
- After the artifact lands, use `implement-with-running-notes.md` to actually execute the top-of-list items; notes file becomes evidence for the next velocity measurement.
