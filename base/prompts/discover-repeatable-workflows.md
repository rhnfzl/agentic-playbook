# Prompt: Discover repeatable workflows worth packaging

Paste the prompt below into your coding agent (Claude Code, Codex, Cursor, Pi, Windsurf, etc.) when you want it to audit your recent work and surface candidates for new skills, subagents, or automations.

The prompt is tool-agnostic. It works against whatever evidence the agent has access to: Claude Code sessions, Codex history, Cursor logs, Pi sessions, Chronicle (if enabled), shell history, or just the files you point it at.

---

```
Look back over my recent work from the last 90 days, or all available history if shorter, and identify repeated manual workflows worth packaging.

Use available evidence in this order:
- Recent Claude Code sessions and task summaries.
- Claude Code Memories and rollout summaries to find patterns repeated across sessions.
- Chronicle, if enabled, to spot repeated work outside Claude Code. Use Chronicle for discovery only; confirm important details in the relevant source system when possible.
- Existing skills, custom agents, and automations, so you reuse or extend what already exists instead of duplicating it.

Look broadly for work that is repeated, time-consuming, error-prone, context-heavy, or benefits from a consistent process. Include workflows across coding, research, writing, planning, communication, operations, analysis, and personal administration.

Only act on a candidate when it:
- occurred at least twice, or is clearly likely to recur and costly to repeat;
- has stable inputs, a repeatable procedure, and a clear output or stopping condition;
- would materially improve speed, quality, consistency, or reliability;
- is not already adequately covered.

Choose the smallest appropriate form:
- Skill: a reusable workflow or playbook.
- Custom subagent: a bounded specialist role or investigation task suitable for delegation.
- Automation: a scheduled or recurring check, report, reminder, or monitor.
- Skip: work that is too one-off, ambiguous, sensitive, or poorly evidenced to package.

First produce a compact shortlist with:
- repeated workflow
- supporting evidence and dates
- frequency/confidence
- recommended form: skill, subagent, automation, extend existing, or skip
- why it is or is not worth creating

Then create only the high-confidence missing items. Keep them narrow, practical, source-aware, and easy to validate. Do not create speculative, overlapping, or overly broad assets.

Finish with:
- what you created or extended
- what you deliberately skipped
- what needs more evidence before packaging
```

## When to use this prompt

- Quarterly, as a periodic sweep of your own coding work to surface skill candidates that emerged organically.
- After a long project or push (sprint, release, incident response) where you have just done a lot of similar tasks back-to-back.
- When onboarding to a new role or codebase and wanting to codify the patterns you have just learned.
- Before scoping a new tooling investment, to check whether the work it would automate is genuinely repeated.

## What this prompt is NOT

- Not a real-time skill (do not invoke mid-task). It is an end-of-period audit.
- Not a substitute for `/playbook-retrospective` (which audits a single session). This prompt is the higher-level sweep across many sessions and many tools.
- Not a substitute for explicit manual authoring when you know exactly what you want to package. Use `add-a-new-skill.md` for that.

## Why it works across agents

The prompt encodes a discipline, not a tool integration. It tells the agent:
1. Use whatever evidence you can access (Claude Code sessions, Codex history, Chronicle, etc.). Be explicit about gaps.
2. Apply four filters before recommending anything (recurrence, stability, value, novelty).
3. Output a structured shortlist before creating anything.
4. Create only the high-confidence subset, and surface what was deliberately skipped.

Any agent that can introspect SOME source of recent work can run this. The bigger the agent's evidence access (Chronicle, multi-session memory, automation logs), the better the output.

## Where the output goes

The agent will propose creating skills, subagents, and automations. In the coding-agents-playbook context, those land as:
- Skills: `skills/<category>/<name>/SKILL.md` (via `make new SKILL=<name>` or directly).
- Subagents: `agents/<name>.md` per the unified schema in `docs/adr/0009-unified-agents-directory.md`.
- Automations: depends on the runtime (cron, GitHub Actions, Codex `~/.codex/automations/`, etc.).

For the more careful flow (interview, owner confirmation, 2nd-source check), have the agent draft proposals into `~/.playbook-proposals/` first, then graduate via `/playbook-promote <slug>`. See `docs/adr/0008-three-layer-capture-system.md`.
