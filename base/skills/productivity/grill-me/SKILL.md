---
name: grill-me
description: Use when the user wants to stress-test a plan or design, says "grill me", or asks to be interviewed before building. Walks down each branch of the decision tree one question at a time, with a recommended answer for each.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [interview, alignment, brainstorming]
scope: [any]
---

# Grill Me

Use when the user wants to stress-test a plan, get grilled on their design, or mentions "grill me". Adapted from mattpocock's `grill-me` (productivity category) and `grill-with-docs` (engineering category) for the team use case.

The point is to surface tradeoffs early, while assumptions are still cheap to change. By the end of a grilling session, every major decision is locked with a documented rationale.

## How it works

For each open decision, ask one question. The question should:

1. **Identify the foundational fork.** Decisions that block other decisions go first.
2. **Provide options with concrete tradeoffs.** Not "what do you want?" Instead: "A, B, or C, and here is why A is recommended."
3. **Include a recommendation.** Always give a recommended answer with rationale. The user can push back, but you must commit to a position.
4. **Resolve dependencies.** Once an answer is locked, the next question often shifts based on what was chosen.

## When the codebase can answer

If a question can be answered by exploring the codebase or documentation (e.g., "what does this existing skill look like?"), do that exploration BEFORE asking the user. Do not ask the user to do work you can do yourself.

## When to stop

Stop when:

- Every major branch of the decision tree is resolved.
- Open questions remaining are implementation details, not architectural choices.

## Output

The interview produces a locked decision tree. Each decision has:

- The question
- The chosen answer
- The rationale
- Any tradeoffs deferred to implementation

End the session by consolidating into a written plan artifact (typically an HTML under `docs/human-html/` in the workspace).

## When NOT to use this skill

- The user already knows what they want and just needs help executing. Grilling adds friction without value when alignment is not the bottleneck.
- The decision is reversible and cheap. Save grilling for choices that are sticky (architecture, naming, format) or expensive to change later.

## Inspiration

This skill is an adaptation of mattpocock's `grill-me` (productivity) and `grill-with-docs` (engineering). See `docs/research/inspirations.md` for the full lineage. The team-specific addition: anchor every recommendation in either research evidence or a documented failure mode it prevents.
