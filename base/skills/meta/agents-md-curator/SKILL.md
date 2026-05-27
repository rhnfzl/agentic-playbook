---
name: agents-md-curator
description: Use when a dev is starting work in a new project and wants a tailored AGENTS.md that their coding agent will auto-load. Interviews them about role, stack, comm preferences, and what to avoid, then assembles a project-level AGENTS.md from playbook templates with a managed block, ending with `@~/AGENTS.md` so global rules flow in. Re-runnable; updates only the managed block.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-26
tags: [onboarding, agents-md, project-setup, meta]
scope: [any]
---

# AGENTS.md Curator

Use when a dev is starting work in a new project and wants a project-level `AGENTS.md` tuned to their role and stack. The skill interviews the dev with five focused questions, picks the right role overlay from `templates/`, fills in the placeholders, and writes (or merges) the result into the project's `AGENTS.md`.

The emitted file is cross-agent: every Tier 1 / Tier 2 adapter the playbook supports reads `AGENTS.md` natively or via `@-import`. The dev does not need a separate `CLAUDE.md`, `.cursor/rules`, `.windsurfrules`, or `.github/copilot-instructions.md` to cover their role.

## When to use

- A dev clones a new project and wants their coding agent to start with full context (their role, their stack, their tone, their hard stops) instead of re-explaining each session.
- A new joiner sets up their first project in a team that uses the playbook and wants the project-level `AGENTS.md` aligned with the playbook's global `~/AGENTS.md`.
- A dev re-runs after their role changes (e.g. moved from backend to tech lead). The managed block updates in place; user-authored sections above and below are preserved.

## When NOT to use

- Do not run on the playbook checkout itself. The playbook's root `AGENTS.md` is a different artifact (project-level rules for the playbook's own contributors). Per ADR-0002, that file is curated by hand.
- Do not run from a directory that is not a project root. The curator writes `./AGENTS.md`; running from a nested directory writes the wrong file. Pause and confirm `pwd` first.
- Do not paste the emitted file into `~/AGENTS.md`. Global org rules belong in `~/AGENTS.md` (managed by `make install`). The curator's output is per-project.

## Procedure

### 1. Confirm scope

Print the absolute path of the current directory and ask the dev to confirm it is the project root. If they are inside a playbook checkout, stop and direct them to the right directory.

### 2. Run the interview

Ask exactly these five questions, one at a time, waiting for each answer:

1. **Role**: one of `product-manager`, `research`, `devops`, `engineering`, `tech-lead`, `qa`. Each maps to a templates/overlay-<role>.md file in this skill directory. If the dev wears multiple hats, pick the one they want this project's AGENTS.md tuned for; they can re-run for the others.
2. **Primary stack**: one short string, e.g. `TypeScript + Next.js + Prisma + PostgreSQL` or `Python + FastAPI + SQLAlchemy + pytest`. This becomes the body of the "Tech stack" lock in `templates/memory.md`.
3. **Communication style**: `terse` or `detailed`. Drives whether the agent should default to short or full responses (used by the "Match response length" rule in `templates/defaults.md`).
4. **What to avoid**: a comma-separated list of patterns or phrasings the agent should never use, e.g. `em dashes, filler phrases like "Great question!", marketing-speak`. Becomes the "Voice" body in `templates/defaults.md`.
5. **One-sentence project goal**: e.g. `Public matching API that recruiters call to fetch ranked talent for a job.` Becomes the "About this project" body in `templates/defaults.md`.

### 3. Assemble the managed block

Read the three core templates from this skill's `templates/` directory:

- `templates/defaults.md` (response style, before significant work, about me, about project, voice)
- `templates/behavior.md` (stay in scope, ask before big changes, confirm destructive, hard stops, show what changed, think before code)
- `templates/memory.md` (decision log, session wrap-up, failure log, tech stack)

Read the role overlay `templates/overlay-<role>.md` matching the dev's answer to question 1.

Substitute the placeholders with the dev's answers:

- `{{ABOUT_ME}}` from question 1 (expand `engineering` to "engineer", `tech-lead` to "tech lead", etc.)
- `{{COMM_STYLE}}` from question 3
- `{{VOICE}}` from question 4 (preface with "Never use:" then list the patterns)
- `{{PROJECT_CONTEXT}}` from question 5
- `{{PROJECT_OR_REPO}}` always renders as `project` (per the v0.10 layered terminology principle; engineers who prefer "repo" can edit the emitted file)
- `{{STACK}}` from question 2

Concatenate the four sections in this order, separated by blank lines:

1. defaults.md (with placeholders filled)
2. behavior.md
3. memory.md (with placeholders filled)
4. overlay-<role>.md

Surround the concatenated content with managed-block markers:

```text
<!-- AGENTS-MD-CURATOR BEGIN -->
... assembled content ...
<!-- AGENTS-MD-CURATOR END -->
```

### 4. Splice into AGENTS.md

If `./AGENTS.md` does not exist, write a new file with this shape:

```markdown
# AGENTS.md

<!-- AGENTS-MD-CURATOR BEGIN -->
... assembled content ...
<!-- AGENTS-MD-CURATOR END -->

@~/AGENTS.md
```

If `./AGENTS.md` exists:

- If it contains a managed block (`<!-- AGENTS-MD-CURATOR BEGIN -->` ... `<!-- AGENTS-MD-CURATOR END -->`), replace the content between the markers. Preserve everything outside the block byte-for-byte.
- If it does not contain a managed block, insert the new block at the top of the file (after the first `#` heading, if any). Preserve everything below the inserted block.
- If the file does not already reference `@~/AGENTS.md`, append it as the last line after a blank line.

### 5. Report

Print a short summary:

- Path of the emitted file.
- Role overlay used.
- Word count of the emitted file (target 450-700 words; outside that range is a soft warning).
- Whether `~/AGENTS.md` was @-imported (yes by default; no only if the dev has not run `make install` on this machine).

## Required Checks

- The dev confirmed the current directory IS the project root (not a nested directory, not the playbook checkout).
- The role answer maps to an existing `templates/overlay-<role>.md` file. If not, ask the dev to pick a closer match before continuing.
- The emitted `AGENTS.md` is valid markdown (no orphan placeholders like `{{ROLE}}` left behind).
- The managed-block markers wrap exactly the assembled content; nothing user-authored leaks inside.

## Do Not

- Do not modify `~/AGENTS.md` from this skill; that file is managed by `make install`.
- Do not pull live content from the web during assembly; templates are the only source of truth for the rules.
- Do not invent new placeholders or skip the role overlay. Each section answers a specific failure mode; partial assembly produces a thin file that does not pull its weight.

## Related skills

- `meta/playbook-promote`: graduates drafts from `~/.playbook-proposals/` into the playbook proper.
- `meta/playbook-retrospective`: end-of-session capture of skill-worthy patterns.
- `productivity/handoff`: structured handoff to another teammate (uses the same managed-block pattern in a different file).

## References

- ADR-0007: claude-md vs agents-md vs skill-md (why this emits `AGENTS.md`, not `CLAUDE.md`).
- ADR-0033: AGENTS.md canonical write API (the managed-block pattern this skill follows).
- CONTEXT.md: glossary entry for "Project" (PM-facing alias for the repo / playbook directory).
