---
name: grill-me
description: Multi-round interview pattern that stress-tests a plan or design by walking down each decision branch one question at a time, with a recommended answer per question.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [interview, alignment, brainstorming, planning, productivity]
---

# Stress-test a plan by walking the decision tree one question at a time

When the user wants to be interviewed before building, this command runs the grill: surface the foundational forks first, ask one question at a time, propose a recommended answer with rationale, and let later questions adapt to the user's earlier choices. By the end, every major decision is locked with a documented rationale.

## When to use

- The user typed `/grill-me` or said "grill me before I build this".
- The user is about to commit to an architecture or naming choice that is sticky or expensive to change later.
- A design has unresolved tradeoffs the user has not yet examined (e.g., where state lives, what the abstraction is, what the rollback path is).
- The user wants a second look before locking a plan into a Jira ticket or HTML decision aid.

## When NOT to use

- The user already knows what they want and just needs help executing. Grilling adds friction without value when alignment is not the bottleneck.
- The decision is reversible and cheap. Save grilling for choices that are sticky (architecture, naming, format) or expensive to change later.
- The user is mid-implementation and wants a debugging walk. Use `/diagnose` instead.
- The user wants to capture session learnings. Use `/playbook-retrospective` instead.

## Your job

You are the interviewer. Ask one question per turn. For each question, do three things: identify the foundational fork, list two to four concrete options with tradeoffs, and commit to a recommended answer with rationale. Resolve dependencies before moving on.

## Workflow

1. **Read what the user has so far.** A plan in Markdown, a PR description, a Jira ticket, a code sketch, a verbal description in the conversation. Identify the open decisions implicit in it.

2. **Order the decisions.** Foundational forks first (decisions that block other decisions). Implementation details last (those are not what grilling is for).

3. **Ask one question.** Format each question as:

   **Question:** What is the choice?
   **Options:**
   - A: brief description, tradeoff.
   - B: brief description, tradeoff.
   - C: brief description, tradeoff.
   **Recommendation:** which option and why.

   Use the `AskUserQuestion` tool if available; otherwise ask in plain prose and wait for an answer.

4. **When the codebase can answer, do not ask.** If a question can be answered by exploring the repo (e.g., "what does this existing skill look like?", "is there already a helper for this?"), do that exploration BEFORE asking. Do not ask the user to do work you can do yourself. Read the relevant files, then refine the question or remove it.

5. **Resolve dependencies as you go.** Once an answer is locked, the next question often shifts based on what was chosen. Re-plan the remaining questions before asking the next one.

6. **Cap the interview.** Stop at around 13 questions for a deep design lock. Stop earlier if every major branch is resolved or remaining questions are implementation details.

7. **Consolidate at the end.** Produce a locked decision tree. Each decision has:
   - The question asked.
   - The chosen answer.
   - The rationale.
   - Any tradeoffs deferred to implementation.

   By default, write the consolidated output to an HTML decision aid under `docs/human-html/<date>-decision-<slug>.html` if the workspace has the human-html harness installed. If not, write Markdown to a temp file and tell the user the path.

## Output

The user sees:

- One question per turn, with options and a recommendation.
- A running summary of locked decisions as the interview progresses.
- A final consolidated decision tree at the end, with all questions, answers, and rationales.
- If applicable, the path of the HTML or Markdown artifact where the tree landed.

## Discipline

- Always commit to a recommendation. "What do you want?" is not grilling; "I recommend A, here is why" is.
- Anchor every recommendation in either research evidence, a documented failure mode it prevents, or a precedent from the codebase.
- Push back on the user when they pick an option that contradicts something earlier in the tree.
- Stop when the remaining questions are no longer architectural.

## Reference

This command is adapted from mattpocock's `grill-me` (productivity) and `grill-with-docs` (engineering) skills. The team-specific addition is that every recommendation is grounded in either evidence (research, codebase, ticket) or a documented failure mode it prevents. See `docs/research/inspirations.md` for the full lineage.
