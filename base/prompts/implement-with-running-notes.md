# Prompt: Implement with running notes

Paste the prompt below when you want a coding agent to implement a non-trivial spec or plan AND keep a running implementation notes file alongside the code. Captures design decisions, deviations, tradeoffs, and open questions in real time so you have a paper trail of how the agent interpreted the spec, not just what the code does.

Different from a normal implementation request because it forces the agent to surface the WHY of every non-obvious choice as a deliverable, not just an artifact of the conversation that gets lost when the session ends.

---

## Canonical template

```
Implement {{PLAN_PATH}} which is based on the {{SPEC_PATH}} specs.

As you work, maintain a running implementation-notes.html file (use the /human-html skill if available, or write to docs/human-html/) that captures anything I should know about how the implementation diverges from or interprets the spec, including:

- Design decisions: choices you made where the spec was ambiguous
- Deviations: places where you intentionally departed from the spec, and why
- Tradeoffs: alternatives you considered and why you picked what you did
- Open questions: anything you'd want me to confirm or revise

Update this file as you go, not at the end. Each entry should reference the spec section or code file it relates to so I can audit it later.
```

## When to use this prompt

- Implementing any spec longer than ~200 lines where you expect ambiguity in places.
- Implementing a plan you wrote in a previous session and want the executor to maintain decision continuity.
- Delegating implementation to a subagent or another teammate via PR description while still owning the decisions.
- Building anything where the rationale matters as much as the code (architectural prototypes, framework choices, public APIs).

## What this prompt is NOT

- Not for tactical fixes (a 5-line bug fix doesn't need a notes file).
- Not a substitute for ADRs. Implementation notes are working artifacts; ADRs are durable decisions. Promote any open question that survives the implementation into an ADR before merge.
- Not for spec-less implementations. If you don't have a spec or plan to point at, use `clarify-then-deliver.md` first to produce one.

## Why a SEPARATE notes file

Most agents will surface design decisions in commit messages or chat. Both lose them: commit messages are scannable but not consultable, and chat history evaporates when the session ends. A dedicated `implementation-notes.html` file:

- Survives the session.
- Lives next to the code (in `docs/human-html/` per the human HTML harness).
- Can be referenced in the PR description.
- Forces the agent to write decisions DOWN rather than just ACT on them.
- Gives the reviewer a "why" doc to read alongside the diff.

## Composition with other prompts

- Pair with `clarify-then-deliver.md` to produce the SPEC first, then this prompt to execute it.
- Pair with `bootstrap-your-playbook.md` for a totally fresh adoption: scaffold the playbook, then implement specific skills with running notes.
- Use the resulting `implementation-notes.html` as evidence input to `discover-repeatable-workflows.md` later: recurring deviations across implementations may surface a pattern worth packaging as a skill.
