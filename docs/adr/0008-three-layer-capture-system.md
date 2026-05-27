# 0008. Three-layer capture system for keeping the playbook updated

## Status
Accepted (2026-05-24)

## Context

A team-shared playbook decays unless there is a mechanism to update it as new patterns emerge during real coding work. Friction is the constraint: capture happens in the middle of someone else's task (a feature, a bug, a meeting), but refinement requires switching context. Two failure modes bracket the design space:

- **Too high-friction**: the user never captures because writing a full SKILL.md inline breaks their work. Discoveries get lost.
- **Too low-friction**: anything goes into the catalog. The playbook accumulates noise, contributors lose trust in it, adoption stalls.

Research (May 2026) surfaced a canonical pattern adopted at production scale by Sionic AI (1000+ ML experiments/day), open-sourced by glebis/claude-skills, and discussed in the AccidentalRebel blog, MindStudio "learnings loop" writeup, and Reddit r/ClaudeCode community: **session-end retrospective + interview-driven promotion**.

## Decision

A three-layer capture system, manual-trigger only at the L2 step.

### Layer 1, Mid-session quick capture

NOT IMPLEMENTED for v0.1. User judgment: "mid-session capture does not make sense; learning evolves." A pattern noticed during a session is often wrong; let it settle.

### Layer 2, Session-end retrospective (`/playbook-retrospective`)

Manual trigger only. The user invokes the skill at end of session. The skill:

1. Reads the current Claude Code session JSONL from `~/.claude/projects/<slug>/<session>.jsonl`.
2. Searches the playbook for existing coverage (no duplicating skills/rules/hooks that already exist).
3. Classifies remaining candidate learnings into skill / rule / hook.
4. Drafts proposals into `$PLAYBOOK_PROPOSALS_DIR` (default `~/.playbook-proposals/`) with proto-frontmatter.
5. Does NOT promote. Drafts sit for at least overnight.

### Layer 3, Periodic cross-session audit

Already implemented as the `/skill-progression-map` Codex automation (created 2026-05-08). Acts as the safety net for things L2 missed. Weekly schedule, recommendation-only, does not create assets autonomously.

### Promotion (`/playbook-promote <slug>`)

Drafts graduate via a separate skill. The promotion:

1. Finds the playbook checkout via `$PLAYBOOK_HOME` or by searching common paths.
2. Reads the draft, parses proto-frontmatter.
3. Runs a grill-me-style interview to ground the pattern in a 2nd source, articulate the "When NOT to use" section, and confirm ownership.
4. Creates a feature branch `feat/playbook-add-<slug>`.
5. Scaffolds via `scripts/new_skill.py` (for skills) or writes directly (for rules / hooks).
6. Runs `make check`.
7. Stops. Final commit, push, and PR creation are the user's job.

## Consequences

- Drafts are private (user-level, gitignored) until promotion. Many "useful patterns" do not survive a second look, and that is intentional.
- The playbook becomes self-improving: the mechanism for updating it lives inside it (`skills/meta/playbook-retrospective`, `skills/meta/playbook-promote`).
- Users adopting the playbook in their own projects can contribute proposals from any working directory; drafts live at `~/.playbook-proposals/` (user-level) rather than inside the playbook checkout.

## Why we chose manual-only L2

User explicitly preferred manual trigger over Stop-hook auto-fire. Reasoning:

- Session-end auto-fire would be noisy on short or trivial sessions.
- The user wants control over when reflection happens.
- If forgetting becomes a problem, the L3 weekly audit catches what L2 missed.

A future ADR may revisit this if the manual-only trigger proves too easy to skip. Possible upgrade path: conditional Stop hook that fires only when the session looks "skill-worthy" (>N edits, inbox has entries, last message contains trigger phrases). That heuristic should be authored by the user, not the system.

## Why drafts live at `~/.playbook-proposals/` not inside the playbook

- Decoupling drafts from the playbook checkout location lets users with different checkout paths (`~/team/...`, `~/projects/...`, `~/work/...`) all share the same proposal workflow.
- Cross-project: a user working across multiple repos has one inbox.
- Works even if the user does not have the playbook cloned locally; the promotion command can fail-fast with a helpful clone instruction.
- Drafts are intentionally private. Promotion is the gate where they become repo-level.

## Configuration

- `PLAYBOOK_PROPOSALS_DIR` (default `~/.playbook-proposals/`): where drafts go.
- `PLAYBOOK_HOME` (default: search common paths): location of the playbook checkout.

## Source

- Sionic AI Hugging Face writeup: `/retrospective` at 1000+ experiments/day scale.
- glebis/claude-skills: Retrospective and Skill Studio.
- AccidentalRebel blog: session-retrospective implementation.
- MindStudio: learnings.md pattern.
- See `docs/research/2026-05-24-research-brief-v1.md` and `v2.md` for citations.
