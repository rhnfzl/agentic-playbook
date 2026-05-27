# Prompt: Clarify then deliver

Paste the prompt below into your coding agent (Claude Code, Codex, Cursor, Pi, Windsurf, etc.) when you want it to GRILL YOU before producing an artifact. The pattern: read context, optionally do background research, interview you with non-obvious questions via the agent's native question tool, iterate until you and the agent have shared understanding, then produce or update the target artifact.

Different from `discover-repeatable-workflows.md` (which is a post-hoc audit of past work). This one is the PRE-WORK clarifying interview before committing to anything.

---

## Canonical template

Fill in the bracketed slots before pasting:

```
[Optional: Read {{CONTEXT_SOURCE}} first.]
[Optional: Spawn subagents to research the references / dependencies / prior art comprehensively.]
[Optional: Use Tavily MCP (or another web research tool) where you lack knowledge or current information before asking questions.]

Interview me in detail using the AskUserQuestion tool (or your agent's native question mechanism) about {{FOCUS_AREA}}: technical implementation, concerns, tradeoffs, edge cases, or anything else you find ambiguous.

Make sure the questions are NOT obvious. Skip anything I have already stated explicitly in the context above. Skip anything an experienced practitioner in this domain would already know. Focus on the decisions where my preference or constraint matters and is not yet captured.

Continue interviewing me continually until the design is complete and you have everything you need.

Then {{DELIVERABLE_ACTION}}.
```

## Example variants (real ones in use)

These are the same prompt instantiated for different deliverables:

**Write a spec from scratch:**

```
Read SPECS.md and interview me in detail using the AskUserQuestion tool about literally anything: technical implementation, concerns, tradeoffs, etc. Make sure the questions are not obvious. Continue interviewing me until it's complete, then write the spec to the file.
```

**Update an existing spec:**

```
Read SPECS.md and interview me in detail using the AskUserQuestion tool about any gaps you see: technical implementation, concerns, tradeoffs, etc. Make sure the questions are not obvious. Continue interviewing me until it's complete, then update the spec.
```

**Build a presentation:**

```
If needed, interview me in detail using the AskUserQuestion tool about literally anything, but make sure the questions are not obvious. Continue interviewing me continually until it's complete, then make me the presentation.
```

**Write a CV or work reference:**

```
If needed, interview me in detail using the AskUserQuestion tool about literally anything, but make sure the questions are not obvious. Continue interviewing me continually until it's complete, then write the report in /path/to/output.md
```

**Estimate hours / produce an estimate:**

```
If needed, interview me in optimised manner using the AskUserQuestion tool about literally anything, but make sure the questions are not obvious. Continue interviewing me continually until it's complete, then provide me the hours.
```

**Research-heavy deep work (subagents + web research):**

```
Read docs/codebase-intelligence-research-session.md and spawn your subagents to understand the provided references comprehensively, thoroughly, and effectively.

Interview me in detail using the AskUserQuestion tool about literally anything: technical implementation, concerns, tradeoffs, etc. Make sure the questions are not obvious, especially what is already in docs/codebase-intelligence-research-session.md.

Use the respective tools you have like Tavily MCP to do your own research where you lack knowledge or understanding before asking questions.

Be very in-depth. Continue interviewing me continually until it's complete, then add/update docs/codebase-intelligence-research-session.md thoroughly where required.
```

**Update AGENTS.md or other agent memory:**

```
If you understood my requirement, and if you need to clarify more, interview me in detail using the AskUserQuestion tool about literally anything: technical, concerns, tradeoffs, etc. Make sure the questions are not obvious. Continue interviewing me continually until it's complete, then update AGENTS.md and the respective markdown files thoroughly where required.
```

(Prefer AGENTS.md over CLAUDE.md as the canonical cross-tool memory surface. Claude Code reads CLAUDE.md natively but the recommended pattern per Anthropic's own docs is `@AGENTS.md` inside CLAUDE.md; updating AGENTS.md propagates to every agent without per-tool duplication.)

## When to use this prompt

- Before writing any non-trivial spec, design doc, or architecture artifact.
- Before authoring a presentation, report, or CV where your specific framing matters.
- Before committing to an implementation path where multiple reasonable choices exist and the wrong one is costly.
- Before estimating effort, where the estimate depends on assumptions the agent should surface.
- When updating an existing artifact and you want the agent to surface gaps you may have missed.

## What this prompt is NOT

- Not for one-shot tactical asks where the answer is obvious from the request itself.
- Not for refactors or code changes that have a clear unambiguous spec already.
- Not a substitute for `/grill-me` skill (which is grilling-only, no artifact production). This prompt INCLUDES artifact production at the end. Pick `/grill-me` when you want pure interrogation; pick this prompt when you want interrogation that ends in something concrete.

## Why "not obvious" is the discipline that matters

The single most important word in this prompt is "not obvious." Without it, agents tend to ask:

- "What language do you want to use?" (already obvious from the codebase)
- "Should I add tests?" (yes, always)
- "Do you want this committed?" (the user will say so when ready)

These wastes the user's time and erodes trust. With the "not obvious" framing, the agent asks:

- "You said the workflow should fail-soft on missing inputs. Should the failure surface as a warning in the install log, or as a non-zero exit code? Trade-off: warnings are easier to ignore in CI; exit codes break automation pipelines we have not seen yet."
- "The existing spec assumes single-tenant. Are we explicitly out-of-scope for multi-tenant in v1, or just deferring? Affects whether the data model should be tenant-aware now."
- "Your constraint says it has to ship in two weeks. Which of these three features can drop if we hit a real blocker on day 5?"

These are the questions that change the artifact.

## Why it works across agents

- Claude Code has the AskUserQuestion tool natively.
- Codex CLI has interactive question flows via its agent contract.
- Cursor has the agent's native ask-clarification mechanism.
- Pi has prompt templates and interactive elicitation.
- Even agents without a structured question tool will pose questions in prose, which the user can still answer.

The prompt encodes a discipline (interrogate before committing, focus on non-obvious decisions, end in a concrete artifact) rather than a tool integration. Any agent that can both ask questions and produce an artifact can run it.

## Composition with other prompts

- Use with `bootstrap-your-playbook.md`: clarify the playbook scope, owner, and decay policy before scaffolding.
- Use with `extract-rules-from-codebase.md`: clarify which rule categories matter to your team before mining.
- Use with `discover-repeatable-workflows.md`: AFTER the audit produces a shortlist, run this prompt to grill on the top 1-2 candidates before authoring.
