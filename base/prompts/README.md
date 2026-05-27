# Pre-built prompts

## What a prompt is in this playbook

A prompt is a self-contained instruction block you paste into your coding agent's chat surface (Claude Code, Cursor, Windsurf, Codex) to drive a specific multi-step workflow. Different from a skill (which the agent invokes when it recognizes a trigger), a rule (always-on constraint), or a command (slash-invokable from the palette). Prompts are user-initiated, explicit, and intentionally portable across agents.

The prompts here encode the *pattern*, not the content. Your team's skills, rules, and conventions will differ from team's; these prompts help the agent build them with your team's specifics, or audit your current setup against this playbook and propose changes.

## Where prompts fit in

| Content type | When it fires | Where the workflow lives |
|---|---|---|
| Rule | Always, before every response | Agent's rules surface (AGENTS.md, .cursor/rules/, ...) |
| Skill | When the agent recognizes a description match | `skills/<cat>/<name>/SKILL.md` |
| Command | User types `/<name>` in the chat palette | `commands/<name>.md` |
| Hook | Lifecycle event (PreToolUse, SessionStart, ...) fires | `hooks/<name>.sh` |
| **Prompt** | **User pastes the prompt block into chat** | **`prompts/<name>.md` (this directory)** |

Prompts are the lowest-ceremony content type. No frontmatter is required, no installer materialization happens; the file is literally a Markdown block the user copy-pastes. The trade-off is that a prompt only runs when a human deliberately reaches for it; the agent will never invoke one on its own.

## How to use

1. Read the prompt to understand what it asks of the agent.
2. Adjust the prompt to your team's specifics (project name, agent of choice, etc.).
3. Paste into your coding agent and follow its lead.

## The prompts

- `bootstrap-your-playbook.md`, paste into your coding agent to scaffold this entire structure for your project
- `add-a-new-skill.md`, walk through adding your workflow as a skill following the pattern (planned, week 3)
- `extract-rules-from-codebase.md`, mine your codebase plus existing agent memory for rules worth lifting (planned, week 3)
- `migrate-personal-skills.md`, convert solo `~/.agents/skills/` into team-shared (planned, week 3)
- `onboard-a-new-teammate.md`, get a new joiner agent-ready in one session (planned, week 3)
- `discover-repeatable-workflows.md`, audit your recent work (last 90 days) across all coding agents to surface candidates for new skills, subagents, and automations. Tool-agnostic: works with whatever evidence each agent can introspect (Claude sessions, Codex history, Chronicle, etc.).
- `clarify-then-deliver.md`, paste before any non-trivial spec / design / presentation / report / estimate. Forces the agent to interview you on the non-obvious decisions first, then produce the artifact. Includes 7 example variants (spec write/update, presentation, CV, hours, research, agent memory).
- `implement-with-running-notes.md`, paste when implementing a spec or plan AND you want a `implementation-notes.html` paper trail of design decisions, deviations, tradeoffs, and open questions captured in real time, not just buried in commit messages.
- `explain-unfamiliar-codebase.md`, paste when you've lost the plot on a codebase and need a single HTML explainer (diagrams, data flow, annotated snippets, gotchas) optimized for "read once and have it all." Uses /human-html for the artifact, /grill-me for non-obvious clarifying questions.
- `prioritize-tickets-with-velocity.md`, paste when you have a backlog that needs sequencing and want estimates grounded in MEASURED velocity (commits, PRs, Jira) rather than gut-feel. Produces an HTML flow + sortable table for stakeholder consumption.

The "I want my coding agent to read this playbook and integrate what fits" Quick Start in the root [README.md](../README.md) bundles two ready-to-paste audit prompts (global + project) that you can grab without opening any file here.

## Design philosophy

The point of having these prompts in the repo is to make the playbook *self-replicating*. A developer at another company can have their AI agent produce a working version of this structure for their stack in 20 minutes by pasting a prompt. The artifact does the adaptation, not the human.

This is the same design move that made `npx create-react-app` succeed. It is also a proof that our own structure holds together: if a prompt can faithfully recreate this for another team, we built something general, not just something that works because we maintain it.
