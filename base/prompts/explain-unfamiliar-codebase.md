# Prompt: Explain an unfamiliar codebase

Paste the prompt below when you've lost the plot on a codebase (yours or someone else's) and need a single artifact that re-grounds you. Produces an HTML explainer with diagrams, data flow, annotated snippets, and gotchas. Optimized for "read once and have it all" rather than "discover progressively."

---

## Canonical template

```
I don't understand how everything works here anymore. Read all the code from {{CODEBASE_DIRECTORIES}} (e.g., ./services/api, ./packages/core, or the whole repo) and produce a single HTML explainer page using the /human-html skill (or write to docs/human-html/ following the YYYY-MM-DD-kind-slug.html naming).

The page must include:
- Architecture diagram of the overall flow (use Mermaid, ASCII, or inline SVG)
- Data flow from {{START_POINT}} (e.g., "user instruction ingestion", "HTTP request entry", "CLI invocation") through every layer to the final output
- Code snippets annotated inline (show the 5-10 most load-bearing functions or classes, with explanations of why they matter)
- "Gotchas" section at the bottom (counter-intuitive behavior, non-obvious dependencies, footguns)

Optimize for someone reading this ONCE with all the context loaded. Plain language FIRST in every section, then progressively delve into developer language. Use first-principles framing: explain what the system DOES for the user before explaining how it does it.

Use the agent's longest-session context if you need to read a lot.

If you need to clarify scope or focus, use the AskUserQuestion tool with /grill-me discipline. Provide detailed multiple-choice options so I can select quickly instead of typing free-form answers.
```

## When to use this prompt

- Returning to a codebase after weeks or months away.
- Onboarding to an unfamiliar repo (yours, an open-source dependency, an inherited codebase).
- Before a major refactor where you need to be sure of the full picture.
- Before delegating work on the codebase to a subagent or teammate; the explainer becomes their briefing.
- After significant churn (multi-PR merge, refactor wave) where the mental model you had is no longer accurate.

## What this prompt is NOT

- Not a substitute for reading the code yourself when correctness matters. The explainer is a navigation aid, not a source of truth.
- Not for narrow questions ("how does feature X work?"). Use a targeted skill or ask directly for that.
- Not for codebases under ~500 lines. Below that, just read the code.

## Why HTML, not Markdown

Markdown loses the value of diagrams, annotated snippets, and visual hierarchy that a re-grounding artifact needs. Per the human-html harness:

- Diagrams render natively (Mermaid, inline SVG).
- Code blocks with syntax highlighting and line-number anchors.
- Collapsible sections for the "gotchas" details that you want present but not in the foreground.
- The artifact lands at `docs/human-html/YYYY-MM-DD-explainer-<slug>.html` with auto-indexing.

The human-html harness is documented in `~/AGENTS.md` (Human HTML Artifacts section) and ships as the `human-html` skill in this playbook.

## Composition with other prompts

- After this prompt produces the explainer, use `clarify-then-deliver.md` to plan any change to the now-understood codebase.
- The explainer's "gotchas" section is a candidate input to `discover-repeatable-workflows.md`: recurring gotchas across multiple explainers might be worth packaging as a rule or skill.
- Pair with `implement-with-running-notes.md` when you need to MODIFY the codebase you just explained: the explainer is the spec, the notes file tracks how you executed against it.
