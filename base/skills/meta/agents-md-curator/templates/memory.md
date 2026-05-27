## Memory and stack

### Decision log

Maintain a file called `MEMORY.md` in this {{PROJECT_OR_REPO}}. After any significant decision, add an entry with:

- What was decided.
- Why.
- What was rejected and why.

Read `MEMORY.md` at the start of every session. Never contradict a logged decision without flagging it first.

### Session wrap-up

When I say "session end", "wrapping up", or "let's stop here": write a session summary to `MEMORY.md` including: worked on, completed, in progress, decisions made, next session priorities.

### Failure log

Maintain a file called `ERRORS.md`. When an approach takes more than 2 attempts to work, log: what did not work, what worked instead, note for next time. Check `ERRORS.md` before suggesting approaches to similar tasks.

### Tech stack

Tech stack for this {{PROJECT_OR_REPO}}. Always use these. Never suggest alternatives unless I ask:

{{STACK}}

If something seems like the wrong tool, flag it. But use the defined stack unless I explicitly say otherwise.

### Permanent facts

These facts apply to every session without exception. If any task conflicts with one, flag it before proceeding:

- This {{PROJECT_OR_REPO}}'s stack is fixed (see above); migrations away from it require an explicit decision logged in `MEMORY.md`.
- External API calls and infrastructure changes go through the confirmation gates in the Behavior section.
- Code I have written is the source of truth; the agent's memory of "what was here before" is not.
