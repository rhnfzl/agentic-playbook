---
name: handoff
description: Compact the current session into a handoff document so a fresh agent or session can continue the work without losing context.
version: 1.0.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [handoff, context, session, continuity, productivity]
---

# Compact this session into a handoff document

When the user wants to pause and pick the work back up later (in a fresh agent, a new session, or with a different teammate), this command writes a temp-file handoff that captures everything a continuing agent needs and drops everything it does not.

## When to use

- The user typed `/handoff` because the session is wrapping but the work continues.
- A long debugging or marathon session has accumulated state across many turns and the user wants a compact snapshot.
- The user is about to switch tools (e.g., Claude Code to Codex) and wants the next agent to start with full context.
- The user wants to share where they left off with a teammate (the handoff doc becomes the starting message).

## When NOT to use

- The user wants a status update for a non-technical stakeholder. Use a Slack brief or a human HTML status artifact instead.
- The work is complete and merged. A handoff is only useful when work continues.
- The user wants a permanent reference doc. Handoffs are transient (written to a temp file, not under `docs/`).
- The user wants a meeting brief. Use the meeting-brief skill instead.

## Your job

You are the agent compacting the session. Write a single Markdown file to a `mktemp` path, structured around what a fresh agent needs in order to continue. Drop everything that does not aid continuation.

## Workflow

1. **Create the temp file.** Run:
   ```bash
   mktemp -t handoff-XXXXXX.md
   ```
   The output is the absolute path where the handoff will land. Read the empty file first (so Edit will accept it later), then write the structured content.

2. **Write the handoff** with these sections:

   **Active task**
   - One paragraph: what the user is trying to accomplish.
   - The ticket key (R8-XXXX or MATCH-XXXX) if there is one, with a link to Jira.

   **State**
   - Current branch (`git rev-parse --abbrev-ref HEAD`).
   - Worktree path (`pwd`).
   - Last commit (`git log -1 --oneline`).
   - Uncommitted changes (`git status --short`), with a one-line summary of what is dirty.

   **Open decisions**
   - Unresolved questions the next session must answer.
   - For each, what the user is leaning toward and why (so the next agent can pick up the thread instead of restarting the debate).

   **Blocked items**
   - Anything waiting on external input: PR review, Jira status change, teammate response, MCP deploy, infra ticket.
   - Who or what is blocking, and what unblocks it.

   **Suggested next steps**
   - Ordered list. First step is the smallest concrete action the next session can take.
   - Where possible, name the command or file path the next session should hit first.

   **Suggested skills**
   - Which skills the next session should load (by name). Reference the skill name only, not its full body.
   - Useful when the next session will likely need `VCS-pr-review`, `diagnose`, `lint-guard`, etc.

3. **Preserve load-bearing context.**
   - Active Jira ticket IDs and their state.
   - Current branch and worktree path.
   - In-flight commits not yet pushed.
   - Active scenario or test failures and their classification (MCP, AI Backend, harness, TM Backend).
   - MCP-first boundary decisions made this session.
   - Tool or approval state for in-flight skill execution.
   - User constraints expressed this session (deadlines, scope boundaries, no-go zones).

4. **Drop noise.**
   - Verbose tool output (search results, file listings) once the relevant snippet is quoted inline.
   - Earlier iteration scratch superseded by later findings.
   - Conversational filler ("sure", "great", "let me check").
   - Full agent transcripts where only the final conclusion is load-bearing.

5. **Avoid duplication.** If a fact is already captured in a PRD, plan, ADR, ticket, commit, or HTML artifact, reference it by path or URL instead of restating it. The handoff should be the smallest pointer-rich doc that lets the next agent rebuild context fast.

6. **Tailor to the user's hint.** If the user passed an argument with `/handoff`, treat it as a description of what the next session will focus on and prioritize the relevant sections accordingly.

## Output

The user sees:

- The absolute path of the handoff temp file (so they can share or move it).
- A one-line summary of what landed in the handoff (the active task and the suggested first next step).
- A reminder that the file is transient: not under `docs/`, not committed.

## Reference

The handoff lives in a temp file, not under `docs/`. For permanent reference docs use a different workflow (HTML artifact under `docs/human-html/` or a Markdown reference under the workspace docs lane). For stakeholder updates use a Slack brief or status HTML.
