---
name: handoff
description: Use when the current conversation needs to be compacted into a document so a fresh agent or session can continue the work without losing context.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-24
tags: [handoff, context, session, continuity, documentation]
scope: [any]
---

# Handoff

Compacts the current conversation into a handoff document so a fresh agent can
continue the work.

## When NOT to use this skill

- The user wants a status update for a human stakeholder. Use `stakeholder-slack-brief`
  or create a human HTML artifact instead.
- The work is complete. A handoff is only useful when work continues.

## Workflow

1. Write a handoff document summarising the current conversation. Save it to a path
   produced by `mktemp -t handoff-XXXXXX.md` (read the file before writing to it).

2. Structure the document around what a fresh agent needs:
   - **Active task**: what the user was trying to accomplish.
   - **State**: branch, worktree path, last-known committed / uncommitted status.
   - **Open decisions**: unresolved questions the next session must answer.
   - **Blocked items**: anything waiting on external input (PR review, Jira status,
     teammate response).
   - **Suggested next steps**: ordered list of actions for the next session.
   - **Suggested skills**: which skills the next session should load.

3. Do not duplicate content already captured in other artifacts (PRDs, plans,
   ADRs, issues, commits, diffs). Reference them by path or URL instead.

4. If the user passed arguments, treat them as a description of what the next
   session will focus on and tailor the doc accordingly.

## Output shape

Return the temp file path so the user can share or move it. Do not write to a
path under `docs/` unless the user asks; the handoff is a transient working doc,
not a durable reference.

## What to preserve

Active Jira ticket IDs and their state, current branch and worktree path, in-flight
commits not yet pushed, active scenario or test failures and their classification,
MCP-first boundary decisions made this session, tool or approval state for in-flight
skill execution, and user constraints expressed this session (deadlines, scope
boundaries, explicit no-go zones).

## What to drop

Verbose tool output (search results, file listings) once the relevant snippet has
been quoted, earlier iteration scratch superseded by later findings, conversational
filler, and full agent transcripts where only the final conclusion is load-bearing.
